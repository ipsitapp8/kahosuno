"""In-memory call rooms: two participants each, with a reconnect grace period."""

import asyncio
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import WebSocket

from app.models.protocol import Mode
from app.services.scam.engine import ScamShield
from app.services.vad import Segmenter


class RoomError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(eq=False)
class Participant:
    id: str
    name: str
    language: str
    consent: bool
    segmenter: Segmenter
    mode: Mode = "auto"
    store_transcript: bool = False
    hello_done: bool = False
    ws: WebSocket | None = None
    ptt_active: bool = False
    ptt_buf: bytearray = field(default_factory=bytearray)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    shield: ScamShield | None = None
    shield_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    tasks: set["asyncio.Task[None]"] = field(default_factory=set)
    removal: "asyncio.Task[None] | None" = None
    said_bye: bool = False  # left on purpose: no reconnect grace period


MAX_STORED_LINES = 500
_SCAM_RANK = {"none": 0, "suspicious": 1, "high": 2}


@dataclass
class TranscriptEntry:
    at: datetime
    language: str
    original: str
    translated: str


@dataclass
class RoomStats:
    """What is kept about a call once it is over: numbers, never audio or names.

    Transcript lines are collected only for people who opted in (`store_transcript`)."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    connected: bool = False  # somebody actually joined, so the call is worth recording
    languages: list[str] = field(default_factory=list)
    total_ms: list[int] = field(default_factory=list)
    errors: int = 0
    max_scam: str = "none"
    lines: list[TranscriptEntry] = field(default_factory=list)

    def note_scam(self, level: str) -> None:
        if _SCAM_RANK.get(level, 0) > _SCAM_RANK[self.max_scam]:
            self.max_scam = level

    def add_line(self, language: str, original: str, translated: str) -> None:
        if len(self.lines) < MAX_STORED_LINES:
            self.lines.append(TranscriptEntry(datetime.now(UTC), language, original, translated))


@dataclass(eq=False)
class Room:
    id: str
    code: str
    participants: dict[str, Participant] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    stats: RoomStats = field(default_factory=RoomStats)

    def peer_of(self, p: Participant) -> Participant | None:
        for other in self.participants.values():
            if other.id != p.id:
                return other
        return None


LeftCallback = Callable[[Room, Participant], Awaitable[None]]
ClosedCallback = Callable[[Room], Awaitable[None]]


class RoomRegistry:
    MAX_PARTICIPANTS = 2

    def __init__(
        self,
        segmenter_factory: Callable[[], Segmenter],
        grace_s: float,
        join_ttl_s: float,
        on_left: LeftCallback | None = None,
        shield_factory: Callable[[], ScamShield | None] | None = None,
        on_closed: ClosedCallback | None = None,
    ) -> None:
        self._on_closed = on_closed
        self._rooms: dict[str, Room] = {}
        self._codes: dict[str, str] = {}
        self._segmenter_factory = segmenter_factory
        self._grace_s = grace_s
        self._join_ttl_s = join_ttl_s
        self._on_left = on_left
        self._shield_factory = shield_factory

    def __len__(self) -> int:
        return len(self._rooms)

    def get(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def by_code(self, code: str) -> Room | None:
        rid = self._codes.get(code)
        return self._rooms.get(rid) if rid else None

    def create_room(self) -> Room:
        while True:
            code = f"{secrets.randbelow(10**6):06d}"
            if code not in self._codes:
                break
        room = Room(id=uuid.uuid4().hex, code=code)
        self._rooms[room.id] = room
        self._codes[code] = room.id
        return room

    def add_participant(self, room: Room, name: str, language: str, consent: bool) -> Participant:
        if len(room.participants) >= self.MAX_PARTICIPANTS:
            raise RoomError("room_full", "Room already has two participants")
        p = Participant(
            id=uuid.uuid4().hex,
            name=name,
            language=language,
            consent=consent,
            segmenter=self._segmenter_factory(),
            shield=self._shield_factory() if self._shield_factory else None,
        )
        room.participants[p.id] = p
        if language not in room.stats.languages:
            room.stats.languages.append(language)
        # A token that is never used must not hold the slot forever.
        self._schedule_removal(room, p, self._join_ttl_s)
        return p

    def attach(self, p: Participant, ws: WebSocket) -> WebSocket | None:
        """Bind a socket to the participant. Returns the previous socket, if any."""
        if p.removal:
            p.removal.cancel()
            p.removal = None
        old, p.ws = p.ws, ws
        p.said_bye = False
        p.segmenter.reset()
        p.ptt_active = False
        p.ptt_buf.clear()
        return old

    def detach(self, room: Room, p: Participant, ws: WebSocket) -> None:
        if p.ws is not ws:  # a newer connection already replaced this one
            return
        p.ws = None
        # Hanging up on purpose leaves at once; only a dropped connection gets the grace period.
        self._schedule_removal(room, p, 0 if p.said_bye else self._grace_s)

    def _schedule_removal(self, room: Room, p: Participant, delay: float) -> None:
        if p.removal:
            p.removal.cancel()
        p.removal = asyncio.create_task(self._remove_after(room, p, delay))

    async def _remove_after(self, room: Room, p: Participant, delay: float) -> None:
        await asyncio.sleep(delay)
        room.participants.pop(p.id, None)
        closed = not room.participants and room.id in self._rooms
        if closed:
            self._rooms.pop(room.id, None)
            self._codes.pop(room.code, None)
        if self._on_left and p.hello_done:
            await self._on_left(room, p)
        if closed and self._on_closed:
            await self._on_closed(room)
