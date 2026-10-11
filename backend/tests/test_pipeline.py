import json

import httpx

from app.core.config import Settings
from app.services.pipeline import (
    AudioEvent,
    DoneEvent,
    TranscriptEvent,
    TranslationPipeline,
    pcm_to_wav,
    split_text,
    wav_to_pcm,
)
from app.services.sarvam import SarvamClient


def test_wav_roundtrip() -> None:
    pcm = b"\x01\x00" * 1600
    assert wav_to_pcm(pcm_to_wav(pcm)) == pcm


def test_split_text_respects_limit_and_keeps_text() -> None:
    text = "Pehla vakya hai. Doosra vakya hai! Teesra? " * 30
    parts = split_text(text, 100)
    assert all(len(p) <= 100 for p in parts)
    assert " ".join(parts).split() == text.split()


def test_split_text_long_without_punctuation() -> None:
    parts = split_text("shabd " * 500, 100)
    assert all(len(p) <= 100 for p in parts)
    assert len(parts) > 1


def test_split_text_devanagari_danda() -> None:
    assert split_text("यह पहला है। यह दूसरा है।", 12) == ["यह पहला है।", "यह दूसरा है।"]


def make_pipeline(calls: list[str]) -> TranslationPipeline:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/speech-to-text":
            return httpx.Response(200, json={"transcript": "ନମସ୍କାର"})
        if request.url.path == "/translate":
            return httpx.Response(200, json={"translated_text": "नमस्ते"})
        body = json.loads(request.content)
        assert body["language_code"] == "hi-IN"
        assert body["pace"] == 1.1
        return httpx.Response(200, content=b"\x01\x02\x03\x04")

    settings = Settings(sarvam_api_key="k")  # type: ignore[arg-type]
    client = SarvamClient(settings, transport=httpx.MockTransport(handler))
    return TranslationPipeline(client, client, client)


async def test_pipeline_event_order_and_latency() -> None:
    calls: list[str] = []
    pipeline = make_pipeline(calls)
    events = [e async for e in pipeline.process(b"\x00\x00" * 160, "kn-IN", "hi-IN", pace=1.1)]

    assert calls == ["/speech-to-text", "/translate", "/text-to-speech/stream"]
    assert isinstance(events[0], TranscriptEvent)
    assert events[0].original == "ନମସ୍କାର"
    assert events[0].translated == "नमस्ते"
    assert isinstance(events[1], AudioEvent)
    assert events[1].pcm == b"\x01\x02\x03\x04"
    done = events[-1]
    assert isinstance(done, DoneEvent)
    lat = done.latency
    assert lat.total_ms >= lat.stt_ms + lat.translate_ms
    assert lat.total_ms >= 0 and lat.tts_ms >= 0
