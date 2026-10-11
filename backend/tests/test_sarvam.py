import base64
import json

import httpx
import pytest

from app.core.config import Settings
from app.services.sarvam import SarvamClient, SarvamError


def make_client(handler: httpx.MockTransport, retries: int = 2) -> SarvamClient:
    settings = Settings(sarvam_api_key="test-key", sarvam_max_retries=retries)  # type: ignore[arg-type]
    return SarvamClient(settings, transport=handler)


async def test_translate_skips_same_language() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    client = make_client(httpx.MockTransport(handler))
    assert await client.translate("namaste", "hi-IN", "hi-IN") == "namaste"


async def test_translate_sends_expected_body() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers["api-subscription-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"translated_text": "नमस्ते"})

    client = make_client(httpx.MockTransport(handler))
    assert await client.translate("namaskar", "kn-IN", "hi-IN") == "नमस्ते"
    assert seen["key"] == "test-key"
    assert seen["body"] == {
        "input": "namaskar",
        "source_language_code": "kn-IN",
        "target_language_code": "hi-IN",
        "model": "sarvam-translate:v1",
        "mode": "formal",
    }


async def test_stt_returns_transcript() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/speech-to-text"
        assert b"saaras:v4" in request.content
        return httpx.Response(200, json={"transcript": "hello"})

    client = make_client(httpx.MockTransport(handler))
    assert await client.speech_to_text(b"RIFF", "en-IN") == "hello"


async def test_tts_joins_audios() -> None:
    parts = [base64.b64encode(b"aa").decode(), base64.b64encode(b"bb").decode()]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["speaker"] == "shubh"
        assert body["speech_sample_rate"] == 16000
        return httpx.Response(200, json={"audios": parts})

    client = make_client(httpx.MockTransport(handler))
    assert await client.text_to_speech("hi", "hi-IN") == b"aabb"


async def test_tts_stream_yields_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["output_audio_codec"] == "linear16"
        return httpx.Response(200, content=b"\x00\x01\x02\x03")

    client = make_client(httpx.MockTransport(handler))
    data = b"".join([c async for c in client.text_to_speech_stream("hi", "hi-IN", pace=1.1)])
    assert data == b"\x00\x01\x02\x03"


async def test_retries_on_429_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"translated_text": "ok"})

    client = make_client(httpx.MockTransport(handler))
    assert await client.translate("a", "en-IN", "hi-IN") == "ok"
    assert calls["n"] == 2


async def test_error_after_retries_raises() -> None:
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(503)), retries=1)
    with pytest.raises(SarvamError):
        await client.translate("a", "en-IN", "hi-IN")


async def test_client_error_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(422, json={"error": "bad"})

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(SarvamError) as exc:
        await client.translate("a", "en-IN", "hi-IN")
    assert exc.value.status == 422
    assert calls["n"] == 1


async def test_missing_key_raises() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    client = SarvamClient(Settings(sarvam_api_key=""), transport=transport)
    with pytest.raises(SarvamError):
        await client.translate("a", "en-IN", "hi-IN")
