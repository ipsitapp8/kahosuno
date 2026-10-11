"""WebSocket call endpoint: /ws/v1/rooms/{room_id}?token=<JWT>."""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol

from fastapi import APIRouter, Query, WebSocket
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.security import TokenError, decode_token
from app.models import protocol as pr
from app.services.metrics import Metrics
from app.services.pipeline import AudioEvent, DoneEvent, PipelineEvent, TranscriptEvent
from app.services.rooms import Participant, Room, RoomRegistry

log = logging.getLogger("call")
router = APIRouter()


class PipelineLike(Protocol):
    def process(
        self,
        pcm: bytes,
        src: str,
        tgt: str,
        pace: float | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[PipelineEvent]: ...


async def send_msg(p: Participant, msg: BaseModel) -> None:
    """Send JSON to a participant; a dead socket never breaks the call."""
    if p.ws is None:
        return
    try:
        await p.ws.send_text(msg.model_dump_json())
    except Exception:
        log.debug("send failed", extra={"participant": p.id})


async def send_audio(p: Participant, pcm: bytes) -> None:
    if p.ws is None:
        return
    try:
        await p.ws.send_bytes(bytes([pr.AUDIO_OUT]) + pcm)
    except Exception:
        log.debug("audio send failed", extra={"participant": p.id})


async def process_utterance(
    pipeline: PipelineLike, metrics: Metrics, room: Room, p: Participant, pcm: bytes
) -> None:
    async with p.lock:  # utterances from one speaker are handled in order
        peer = room.peer_of(p)
        if peer is None or not peer.hello_done:
            return
        uid = uuid.uuid4().hex[:8]
        speaking = True
        try:
            async for ev in pipeline.process(pcm, p.language, peer.language):
                if isinstance(ev, TranscriptEvent):
                    if not ev.translated.strip():
                        speaking = False
                        continue
                    for who, listener in (("self", p), ("peer", peer)):
                        await send_msg(
                            listener,
                            pr.Transcript(
                                utterance_id=uid,
                                speaker=who,
                                original=ev.original,
                                translated=ev.translated,
                            ),
                        )
                    await send_msg(peer, pr.TtsStart(utterance_id=uid))
                    shield_task = asyncio.create_task(run_shield(p, peer, ev.original))
                    p.tasks.add(shield_task)
                    shield_task.add_done_callback(p.tasks.discard)
                elif isinstance(ev, AudioEvent):
                    await send_audio(peer, ev.pcm)
                elif isinstance(ev, DoneEvent) and speaking:
                    await send_msg(peer, pr.TtsEnd(utterance_id=uid))
                    lat = ev.latency
                    msg = pr.LatencyMsg(
                        utterance_id=uid,
                        stt_ms=lat.stt_ms,
                        translate_ms=lat.translate_ms,
                        tts_ms=lat.tts_ms,
                        total_ms=lat.total_ms,
                    )
                    await send_msg(p, msg)
                    await send_msg(peer, msg)
                    metrics.utterances += 1
                    for stage in ("stt_ms", "translate_ms", "tts_ms", "total_ms"):
                        metrics.record(stage, getattr(lat, stage))
        except Exception:
            metrics.errors += 1
            log.exception("utterance failed", extra={"participant": p.id})
            await send_msg(
                p, pr.ErrorMsg(code="upstream_failed", message="Could not translate, try again")
            )


def start_utterance(
    pipeline: PipelineLike, metrics: Metrics, room: Room, p: Participant, pcm: bytes
) -> None:
    task = asyncio.create_task(process_utterance(pipeline, metrics, room, p, pcm))
    p.tasks.add(task)
    task.add_done_callback(p.tasks.discard)


async def run_shield(p: Participant, listener: Participant, text: str) -> None:
    """Score what `p` just said and warn `listener` (never `p`). Must never break the call."""
    if p.shield is None:
        return
    try:
        async with p.shield_lock:  # turns are scored in order
            async for alert in p.shield.on_turn(text):
                await send_msg(listener, alert)
    except Exception:
        log.exception("scam shield failed", extra={"participant": p.id})


async def notify_left(room: Room, gone: Participant) -> None:
    for other in room.participants.values():
        await send_msg(other, pr.PeerLeft(name=gone.name, language=gone.language))


async def handle_text(
    app_state: Any, room: Room, p: Participant, ws: WebSocket, text: str
) -> bool:
    """Handle one control message. Returns False when the session should end."""
    try:
        msg = pr.parse_client_message(text)
    except ValidationError:
        await send_msg(p, pr.ErrorMsg(code="bad_message", message="Unknown or invalid message"))
        return True

    if isinstance(msg, pr.Hello):
        if not msg.consent:
            await send_msg(
                p, pr.ErrorMsg(code="consent_required", message="Consent is required", fatal=True)
            )
            await ws.close(code=4403)
            return False
        if msg.language != p.language:
            await send_msg(p, pr.ErrorMsg(code="bad_message", message="Language mismatch"))
            return True
        p.mode, p.store_transcript, p.hello_done = msg.mode, msg.store_transcript, True
        peer = room.peer_of(p)
        info = pr.PeerInfo(name=peer.name, language=peer.language) if peer else None
        await send_msg(p, pr.Joined(participant_id=p.id, peer=info))
        if peer and peer.hello_done:
            await send_msg(peer, pr.PeerJoined(name=p.name, language=p.language))
    elif not p.hello_done:
        await send_msg(p, pr.ErrorMsg(code="bad_message", message="Send hello first"))
    elif isinstance(msg, pr.SetMode):
        p.mode = msg.mode
        p.segmenter.reset()
        p.ptt_active = False
        p.ptt_buf.clear()
    elif isinstance(msg, pr.PttStart):
        p.ptt_active = True
        p.ptt_buf.clear()
    elif isinstance(msg, pr.PttEnd):
        p.ptt_active = False
        if p.ptt_buf:
            start_utterance(app_state.pipeline, app_state.metrics, room, p, bytes(p.ptt_buf))
            p.ptt_buf.clear()
    elif isinstance(msg, pr.Ping):
        await send_msg(p, pr.Pong())
    elif isinstance(msg, pr.Bye):
        return False
    return True


async def handle_audio(app_state: Any, room: Room, p: Participant, data: bytes) -> None:
    settings: Settings = app_state.settings
    if not p.hello_done:
        await send_msg(p, pr.ErrorMsg(code="bad_message", message="Send hello first"))
        return
    if not data or data[0] != pr.AUDIO_IN:
        await send_msg(p, pr.ErrorMsg(code="bad_message", message="Unknown audio frame type"))
        return
    payload = data[1:]
    if len(payload) > settings.max_frame_bytes:
        await send_msg(p, pr.ErrorMsg(code="frame_too_large", message="Audio frame too large"))
        return
    if p.mode == "auto":
        for utt in p.segmenter.feed(payload):
            start_utterance(app_state.pipeline, app_state.metrics, room, p, utt)
    elif p.ptt_active:
        if len(p.ptt_buf) + len(payload) > settings.max_utterance_s * 16000 * 2:
            p.ptt_active = False
            p.ptt_buf.clear()
            await send_msg(
                p, pr.ErrorMsg(code="utterance_too_long", message="Held for too long, try again")
            )
            return
        p.ptt_buf += payload


@router.websocket("/ws/v1/rooms/{room_id}")
async def call_socket(ws: WebSocket, room_id: str, token: str = Query("")) -> None:
    state = ws.app.state
    registry: RoomRegistry = state.registry
    await ws.accept()

    async def reject(code: str, message: str, close: int) -> None:
        await ws.send_text(pr.ErrorMsg(code=code, message=message, fatal=True).model_dump_json())
        await ws.close(code=close)

    try:
        claims = decode_token(state.settings, token)
    except TokenError:
        await reject("bad_token", "Invalid or expired token", 4401)
        return
    room = registry.get(room_id)
    if room is None or claims.get("rid") != room_id or claims.get("pid") not in room.participants:
        await reject("room_not_found", "Room not found", 4404)
        return

    p = room.participants[claims["pid"]]
    old = registry.attach(p, ws)
    if old is not None:
        try:
            await old.close(code=4409)
        except Exception:
            pass
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            try:
                if msg.get("bytes") is not None:
                    await handle_audio(state, room, p, msg["bytes"])
                elif msg.get("text") is not None:
                    if not await handle_text(state, room, p, ws, msg["text"]):
                        break
            except Exception:  # a bad message must never end the call
                state.metrics.errors += 1
                log.exception("message handling failed", extra={"participant": p.id})
    finally:
        registry.detach(room, p, ws)
