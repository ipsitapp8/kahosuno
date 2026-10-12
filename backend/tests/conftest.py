from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.pipeline import (
    AudioEvent,
    DoneEvent,
    Latency,
    PipelineEvent,
    TranscriptEvent,
)


class FakePipeline:
    """Stands in for TranslationPipeline: no network, records what it was given."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str]] = []
        self.fail = False
        self.transcript = "ନମସ୍କାର"

    async def process(
        self,
        pcm: bytes,
        src: str,
        tgt: str,
        pace: float | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[PipelineEvent]:
        self.calls.append((len(pcm), src, tgt))
        if self.fail:
            raise RuntimeError("sarvam down")
        yield TranscriptEvent(self.transcript, "नमस्ते", 10, 20)
        yield AudioEvent(b"\x01\x00" * 100)
        yield AudioEvent(b"\x02\x00" * 100)
        yield DoneEvent(Latency(10, 20, 5, 40))


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "jwt_secret": "test-secret-0123456789-0123456789-xyz",
        "sarvam_api_key": "",
        "database_url": "sqlite+aiosqlite:///:memory:",
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def pipeline() -> FakePipeline:
    return FakePipeline()


@pytest.fixture
def client(pipeline: FakePipeline) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(reconnect_grace_s=0.3), pipeline)) as tc:
        yield tc
