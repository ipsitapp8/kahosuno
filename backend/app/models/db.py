"""Database tables. Privacy by design: there is no column for audio, names or phone numbers."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CallRecord(Base):
    """One finished call: numbers only."""

    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime] = mapped_column(DateTime)
    duration_s: Mapped[int] = mapped_column(Integer)
    languages: Mapped[str] = mapped_column(String(64))  # e.g. "kn-IN,hi-IN"
    utterances: Mapped[int] = mapped_column(Integer)
    avg_total_ms: Mapped[int] = mapped_column(Integer)
    p95_total_ms: Mapped[int] = mapped_column(Integer)
    errors: Mapped[int] = mapped_column(Integer)
    max_scam: Mapped[str] = mapped_column(String(12))  # none / suspicious / high


class TranscriptLine(Base):
    """Only written for a speaker who opted in. Never linked to a name."""

    __tablename__ = "transcript_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    at: Mapped[datetime] = mapped_column(DateTime)
    language: Mapped[str] = mapped_column(String(8))
    original: Mapped[str] = mapped_column(Text)
    translated: Mapped[str] = mapped_column(Text)
