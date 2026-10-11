import base64
import json

import httpx
import pytest

from app.core.config import Settings
from app.services.factory import build_providers
from app.services.gnani import GnaniClient, GnaniError
from app.services.indictrans2 import IndicTrans2Translate
from app.services.sarvam import SarvamClient


def make_client(handler: httpx.MockTransport, key: str = "gk") -> GnaniClient:
    settings = Settings(gnani_api_key=key, gnani_max_retries=1)  # type: ignore[arg-type]
    return GnaniClient(settings, transport=handler)


async def test_stt_request_shape() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-api-key-id"]
        seen["body"] = request.content
        return httpx.Response(200, json={"success": True, "transcript": "ನಮಸ್ಕಾರ"})

    client = make_client(httpx.MockTransport(handler))
    assert await client.speech_to_text(b"RIFFwav", "kn-IN") == "ನಮಸ್ಕಾರ"
    assert seen["url"] == "https://api.vachana.ai/stt/v3"
    assert seen["key"] == "gk"
    body = seen["body"]
    assert isinstance(body, bytes)
    for needle in (b'name="audio_file"', b'name="language_code"', b"kn-IN", b"transcribe"):
        assert needle in body


async def test_stt_rejects_odia_without_calling_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(GnaniError, match="does not support od-IN"):
        await client.speech_to_text(b"x", "od-IN")


async def test_missing_key() -> None:
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200)), key="")
    with pytest.raises(GnaniError, match="GNANI_API_KEY"):
        await client.speech_to_text(b"x", "hi-IN")


async def test_stt_retries_on_503() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"transcript": "ok"})

    client = make_client(httpx.MockTransport(handler))
    assert await client.speech_to_text(b"x", "hi-IN") == "ok"
    assert calls["n"] == 2


async def test_stt_403_is_error_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, json={"success": False, "error": {"type": "FORBIDDEN"}})

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(GnaniError) as exc:
        await client.speech_to_text(b"x", "hi-IN")
    assert exc.value.status == 403 and calls["n"] == 1


def sse(*events: tuple[str, dict[str, object]]) -> bytes:
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events).encode()


async def test_tts_stream_parses_sse_and_maps_speed() -> None:
    a, b = base64.b64encode(b"\x01\x02").decode(), base64.b64encode(b"\x03\x04").decode()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/v1/tts/sse"
        assert body["voice"] == "Saanvi" and body["language"] == "kn-IN"
        assert body["model"] == "timbre-v2.5"
        assert body["speed"] == 1.15  # pace 1.4 is clamped to Timbre's range
        assert body["audio_config"]["sample_rate"] == 16000
        assert body["audio_config"]["container"] == "raw"
        return httpx.Response(
            200,
            content=sse(
                ("start", {"status": "streaming_started"}),
                ("chunk", {"chunk_index": 0, "audio": a, "is_final": False}),
                ("chunk", {"chunk_index": 1, "audio": b, "is_final": False}),
                ("complete", {"chunk_index": 2, "audio": "", "is_final": True}),
            ),
        )

    client = make_client(httpx.MockTransport(handler))
    chunks = [c async for c in client.text_to_speech_stream("ನಮಸ್ಕಾರ", "kn-IN", pace=1.4)]
    assert chunks == [b"\x01\x02", b"\x03\x04"]


async def test_tts_stream_error_event_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse(("error", {"message": "boom"})))

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(GnaniError):
        [c async for c in client.text_to_speech_stream("x", "hi-IN")]


async def test_tts_stream_http_error_raises() -> None:
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    with pytest.raises(GnaniError) as exc:
        [c async for c in client.text_to_speech_stream("x", "hi-IN")]
    assert exc.value.status == 429


async def test_tts_rest_returns_raw_pcm() -> None:
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200, content=b"\x09\x08")))
    assert await client.text_to_speech("नमस्ते", "hi-IN") == b"\x09\x08"


async def test_tts_unknown_language_voice() -> None:
    client = make_client(httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(GnaniError, match="No Gnani voice"):
        await client.text_to_speech("x", "od-IN")


def test_default_providers_are_gnani_voice_sarvam_translate() -> None:
    p = build_providers(Settings())
    assert isinstance(p.stt, GnaniClient) and isinstance(p.tts, GnaniClient)
    assert isinstance(p.translate, SarvamClient)


def test_providers_swap_by_config() -> None:
    p = build_providers(
        Settings(stt_provider="sarvam", tts_provider="sarvam", translate_provider="indictrans2")
    )
    assert isinstance(p.stt, SarvamClient) and isinstance(p.tts, SarvamClient)
    assert isinstance(p.translate, IndicTrans2Translate)


def test_unknown_provider_name_fails_loudly() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        build_providers(Settings(stt_provider="nope"))
    with pytest.raises(ValueError, match="translate provider"):
        build_providers(Settings(translate_provider="nope"))


async def test_indictrans2_stub_is_explicit() -> None:
    it2 = IndicTrans2Translate()
    assert await it2.translate("same", "hi-IN", "hi-IN") == "same"
    with pytest.raises(NotImplementedError):
        await it2.translate("x", "kn-IN", "hi-IN")


async def test_sarvam_translate_uses_formal_mode_for_sarvam_translate_model() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"translated_text": "x"})

    settings = Settings(sarvam_api_key="k", translate_model="sarvam-translate:v1")  # type: ignore[arg-type]
    client = SarvamClient(settings, transport=httpx.MockTransport(handler))
    await client.translate("a", "kn-IN", "hi-IN")
    assert seen["model"] == "sarvam-translate:v1" and seen["mode"] == "formal"


def wav_header(data_len: int) -> bytes:
    return (
        b"RIFF" + (36 + data_len).to_bytes(4, "little") + b"WAVEfmt "
        + (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
        + b"data" + data_len.to_bytes(4, "little")
    )


def test_strip_wav_header() -> None:
    from app.services.gnani import strip_wav_header

    pcm = b"\x10\x00\x20\x00"
    assert len(wav_header(4)) == 44
    assert strip_wav_header(wav_header(4) + pcm) == pcm
    assert strip_wav_header(pcm) == pcm  # raw PCM is untouched
    assert strip_wav_header(wav_header(0)) == b""  # header-only chunk


async def test_tts_stream_strips_header_only_from_first_chunk() -> None:
    first = wav_header(4) + b"\x01\x00\x02\x00"
    # A later chunk that happens to begin with the bytes "RIFF" is audio, not a header.
    second = b"RIFF" + b"\x00\x00"
    enc = [base64.b64encode(x).decode() for x in (first, second)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=sse(
                ("chunk", {"chunk_index": 0, "audio": enc[0], "is_final": False}),
                ("chunk", {"chunk_index": 1, "audio": enc[1], "is_final": False}),
                ("complete", {"chunk_index": 2, "audio": "", "is_final": True}),
            ),
        )

    client = make_client(httpx.MockTransport(handler))
    chunks = [c async for c in client.text_to_speech_stream("x", "hi-IN")]
    assert chunks == [b"\x01\x00\x02\x00", b"RIFF\x00\x00"]
    assert not any(c.startswith(b"RIFF" + (40).to_bytes(4, "little")) for c in chunks)
