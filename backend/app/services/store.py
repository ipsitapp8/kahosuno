"""Call metadata storage (SQLite via async SQLAlchemy)."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.models.db import Base, CallRecord, TranscriptLine
from app.services.rooms import Room

log = logging.getLogger("store")


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


class CallStore:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url)
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    async def init(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()

    async def save_room(self, room: Room) -> int | None:
        """Record a finished call. Returns the new id, or None if there was nothing to record."""
        s = room.stats
        if not s.connected:
            return None
        ended = datetime.now(UTC)
        record = CallRecord(
            started_at=s.started_at.replace(tzinfo=None),
            ended_at=ended.replace(tzinfo=None),
            duration_s=max(0, int((ended - s.started_at).total_seconds())),
            languages=",".join(s.languages),
            utterances=len(s.total_ms),
            avg_total_ms=round(sum(s.total_ms) / len(s.total_ms)) if s.total_ms else 0,
            p95_total_ms=_p95(s.total_ms),
            errors=s.errors,
            max_scam=s.max_scam,
        )
        async with self._sessions() as session:
            session.add(record)
            await session.flush()
            for line in s.lines:  # empty unless a speaker opted in
                session.add(
                    TranscriptLine(
                        call_id=record.id,
                        at=line.at.replace(tzinfo=None),
                        language=line.language,
                        original=line.original,
                        translated=line.translated,
                    )
                )
            await session.commit()
            return record.id

    async def save_room_safely(self, room: Room) -> None:
        """For use as a background callback: a database problem must never hurt a call."""
        try:
            await self.save_room(room)
        except Exception:
            log.exception("could not save call record")

    async def prune_transcripts(self, older_than_days: int) -> int:
        """Delete stored transcript lines past the retention period."""
        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).replace(tzinfo=None)
        async with self._sessions() as session:
            result = await session.execute(delete(TranscriptLine).where(TranscriptLine.at < cutoff))
            await session.commit()
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def recent_calls(self, limit: int = 20) -> list[CallRecord]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(CallRecord).order_by(CallRecord.id.desc()).limit(limit)
            )
            return list(rows)
