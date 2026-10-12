"""Privacy: what is stored after a call (and, as importantly, what is not)."""

import logging
import sqlite3
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.db import CallRecord, TranscriptLine
from app.services.rooms import Room
from app.services.store import CallStore
from tests.conftest import FakePipeline, make_settings
from tests.helpers import speech_pcm
from tests.test_call_e2e import HI, OD, collect_until, hello, open_room, recv, speak, url


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "calls.db"


@pytest.fixture
def pipeline() -> FakePipeline:
    return FakePipeline()


@pytest.fixture
def client(db_path: Path, pipeline: FakePipeline) -> Iterator[TestClient]:
    settings = make_settings(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}", reconnect_grace_s=0.3
    )
    with TestClient(create_app(settings, pipeline)) as tc:
        yield tc


def rows(db: Path, sql: str) -> list[tuple[object, ...]]:
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def wait_for(db: Path, sql: str, count: int = 1, timeout: float = 5.0) -> list[tuple[object, ...]]:
    deadline = time.time() + timeout
    found: list[tuple[object, ...]] = []
    while time.time() < deadline:
        try:
            found = rows(db, sql)
        except sqlite3.OperationalError:
            found = []
        if len(found) >= count:
            return found
        time.sleep(0.05)
    return found


def talk(
    client: TestClient, pipeline: FakePipeline, a_opts: dict[str, object], b_opts: dict[str, object]
) -> None:
    """A speaks, then B speaks, then both hang up."""
    a, b = open_room(client)
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        hello(wa, OD, **a_opts)
        recv(wa)
        hello(wb, HI, **b_opts)
        recv(wb)
        recv(wa)  # peer_joined

        pipeline.transcript = "AAA-spoken-by-A"
        speak(wa, speech_pcm())
        collect_until(wb, "latency")
        collect_until(wa, "latency")

        pipeline.transcript = "BBB-spoken-by-B"
        speak(wb, speech_pcm())
        collect_until(wa, "latency")
        collect_until(wb, "latency")

        wa.send_json({"v": 1, "type": "bye"})
        wb.send_json({"v": 1, "type": "bye"})


def test_call_is_recorded_as_numbers_only(
    client: TestClient, pipeline: FakePipeline, db_path: Path
) -> None:
    talk(client, pipeline, {}, {})
    calls = wait_for(db_path, "SELECT utterances, languages, max_scam, errors FROM calls")
    assert len(calls) == 1
    utterances, languages, max_scam, errors = calls[0]
    assert utterances == 2
    assert set(str(languages).split(",")) == {"kn-IN", "hi-IN"}
    assert max_scam == "none" and errors == 0
    assert rows(db_path, "SELECT * FROM transcript_lines") == []  # nothing was opted in


def test_transcript_is_stored_only_for_the_speaker_who_opted_in(
    client: TestClient, pipeline: FakePipeline, db_path: Path
) -> None:
    talk(client, pipeline, {"store_transcript": True}, {"store_transcript": False})
    wait_for(db_path, "SELECT id FROM calls")
    lines = wait_for(db_path, "SELECT language, original FROM transcript_lines")
    assert [(lang, text) for lang, text in lines] == [("kn-IN", "AAA-spoken-by-A")]
    everything = str(rows(db_path, "SELECT * FROM transcript_lines")) + str(
        rows(db_path, "SELECT * FROM calls")
    )
    assert "BBB-spoken-by-B" not in everything  # B did not opt in


def test_tables_have_no_place_for_audio_or_identity(client: TestClient, db_path: Path) -> None:
    wait_for(db_path, "SELECT name FROM sqlite_master WHERE type='table'", count=2)
    columns = {
        row[1].lower()
        for table in ("calls", "transcript_lines")
        for row in rows(db_path, f"PRAGMA table_info({table})")
    }
    for forbidden in ("audio", "pcm", "wav", "name", "phone", "ip", "token", "participant"):
        assert not any(forbidden == c or forbidden in c.split("_") for c in columns), forbidden


def test_scam_level_is_remembered(
    client: TestClient, pipeline: FakePipeline, db_path: Path
) -> None:
    a, b = open_room(client)
    pipeline.transcript = "मैं बैंक से बोल रहा हूँ, तुरंत अपना ओटीपी बताइए।"
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        hello(wa, OD)
        recv(wa)
        hello(wb, HI)
        recv(wb)
        recv(wa)
        speak(wa, speech_pcm())
        collect_until(wb, "scam_alert")
        wa.send_json({"v": 1, "type": "bye"})
        wb.send_json({"v": 1, "type": "bye"})
    calls = wait_for(db_path, "SELECT max_scam FROM calls")
    assert calls == [("high",)]


def test_a_room_nobody_joined_leaves_no_record() -> None:
    settings = make_settings(join_ttl_s=0.2, database_url="sqlite+aiosqlite:///:memory:")
    app = create_app(settings, FakePipeline())
    with TestClient(app) as tc:
        open_room(tc)
        time.sleep(0.8)  # the unused seats expire and the room closes
        assert len(app.state.registry) == 0
    # (nothing to read back from :memory:, but save_room() itself refuses unconnected rooms)


def test_logs_never_contain_what_was_said(
    client: TestClient, pipeline: FakePipeline, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    marker = "ULTRA-PRIVATE-PHRASE-12345"
    a, b = open_room(client)
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        hello(wa, OD, store_transcript=True)
        recv(wa)
        hello(wb, HI)
        recv(wb)
        recv(wa)
        pipeline.transcript = marker
        speak(wa, speech_pcm())
        collect_until(wb, "latency")
        pipeline.fail = True  # the error path logs a traceback: it must not carry speech either
        speak(wa, speech_pcm())
        collect_until(wa, "error")
        wa.send_json({"v": 1, "type": "bye"})
    leaked = [r for r in caplog.records if marker in r.getMessage() or marker in str(r.__dict__)]
    assert leaked == []
    assert marker not in caplog.text


# ---- the store on its own ----
async def test_retention_deletes_old_transcript_lines_but_keeps_call_numbers(
    tmp_path: Path,
) -> None:
    store = CallStore(f"sqlite+aiosqlite:///{(tmp_path / 's.db').as_posix()}")
    await store.init()
    now = datetime.now(UTC).replace(tzinfo=None)
    async with store._sessions() as session:
        session.add(
            CallRecord(
                started_at=now,
                ended_at=now,
                duration_s=5,
                languages="kn-IN",
                utterances=2,
                avg_total_ms=1,
                p95_total_ms=1,
                errors=0,
                max_scam="none",
            )
        )
        await session.flush()
        for age_days in (1, 30):
            session.add(
                TranscriptLine(
                    call_id=1,
                    at=now - timedelta(days=age_days),
                    language="kn-IN",
                    original=f"line {age_days} days old",
                    translated="x",
                )
            )
        await session.commit()

    assert await store.prune_transcripts(older_than_days=7) == 1
    async with store._sessions() as session:
        left = (await session.execute(TranscriptLine.__table__.select())).fetchall()
    assert [row.original for row in left] == ["line 1 days old"]
    assert len(await store.recent_calls()) == 1
    await store.close()


async def test_unconnected_room_is_not_saved(tmp_path: Path) -> None:
    store = CallStore(f"sqlite+aiosqlite:///{(tmp_path / 's.db').as_posix()}")
    await store.init()
    assert await store.save_room(Room(id="r", code="000000")) is None
    assert await store.recent_calls() == []
    await store.close()


async def test_database_failure_never_raises_into_the_call(tmp_path: Path) -> None:
    store = CallStore(
        f"sqlite+aiosqlite:///{(tmp_path / 'nope' / 's.db').as_posix()}"
    )  # no such dir
    room = Room(id="r", code="000000")
    room.stats.connected = True
    await store.save_room_safely(room)  # logs the problem, does not raise
