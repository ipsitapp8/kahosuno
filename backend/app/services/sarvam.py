"""Async client for the Sarvam AI REST APIs (STT, translate, TTS, chat)."""

import asyncio
import base64
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import Settings, get_settings

# Speaker per language. Not yet verified against bulbul:v3: the voices page does not list
# these names, so the Phase 2 smoke test must confirm them (and an Odia voice).
VOICES: dict[str, str] = {
    "hi-IN": "shubh",
    "od-IN": "priya",
    "bn-IN": "aditya",
    "en-IN": "ritu",
    "pa-IN": "rahul",
}

RETRY_STATUS = {429, 502, 503, 504}


class SarvamError(Exception):
    """Raised when a Sarvam call fails after retries."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class SarvamClient:
    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._s = settings or get_settings()
        self._http = httpx.AsyncClient(
            base_url=self._s.sarvam_base_url,
            timeout=httpx.Timeout(self._s.sarvam_timeout_s),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        key = self._s.sarvam_api_key.get_secret_value()
        if not key:
            raise SarvamError("SARVAM_API_KEY is not set")
        return {"api-subscription-key": key}

    async def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        """POST with exponential backoff on 429/5xx and network errors."""
        attempts = self._s.sarvam_max_retries + 1
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = await self._http.post(path, headers=self._headers(), **kwargs)
            except httpx.TransportError as exc:
                last = exc
            else:
                if resp.status_code not in RETRY_STATUS:
                    if resp.is_error:
                        raise SarvamError(
                            f"{path} failed: {resp.status_code} {resp.text[:200]}",
                            resp.status_code,
                        )
                    return resp
                last = SarvamError(f"{path} returned {resp.status_code}", resp.status_code)
            if attempt < attempts - 1:
                await asyncio.sleep(0.4 * 2**attempt)
        if isinstance(last, SarvamError):
            raise last
        raise SarvamError(f"{path} failed: {last!r}")

    async def speech_to_text(self, wav_bytes: bytes, lang: str) -> str:
        resp = await self._post(
            "/speech-to-text",
            files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            data={"model": self._s.stt_model, "language_code": lang},
        )
        return str(resp.json()["transcript"])

    async def translate(self, text: str, src: str, tgt: str) -> str:
        if src == tgt or not text.strip():
            return text
        resp = await self._post(
            "/translate",
            json={
                "input": text,
                "source_language_code": src,
                "target_language_code": tgt,
                "model": self._s.translate_model,
                "mode": self._s.translate_mode,
            },
        )
        return str(resp.json()["translated_text"])

    def _tts_body(
        self, text: str, lang: str, pace: float | None, temperature: float | None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "text": text,
            "language_code": lang,
            "model": self._s.tts_model,
            "speaker": VOICES[lang],
            "speech_sample_rate": 16000,
        }
        if pace is not None:
            body["pace"] = pace
        if temperature is not None:
            body["temperature"] = temperature
        return body

    async def text_to_speech(
        self,
        text: str,
        lang: str,
        pace: float | None = None,
        temperature: float | None = None,
    ) -> bytes:
        """REST TTS. Returns the decoded WAV chunks joined together."""
        body = self._tts_body(text, lang, pace, temperature)
        resp = await self._post("/text-to-speech", json=body)
        return b"".join(base64.b64decode(a) for a in resp.json()["audios"])

    async def text_to_speech_stream(
        self,
        text: str,
        lang: str,
        pace: float | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[bytes]:
        """HTTP-streaming TTS: yields raw linear16 PCM chunks as they arrive."""
        body = self._tts_body(text, lang, pace, temperature)
        body["output_audio_codec"] = "linear16"
        async with self._http.stream(
            "POST", "/text-to-speech/stream", headers=self._headers(), json=body
        ) as resp:
            if resp.is_error:
                detail = (await resp.aread()).decode(errors="replace")[:200]
                raise SarvamError(
                    f"tts stream failed: {resp.status_code} {detail}", resp.status_code
                )
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk

    async def chat_json(self, system: str, user: str, max_tokens: int = 400) -> str:
        """Chat completion in JSON mode with reasoning off. Returns message content."""
        resp = await self._post(
            "/v1/chat/completions",
            json={
                "model": self._s.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "reasoning_effort": None,
                "temperature": 0.1,
                "max_tokens": max_tokens,
            },
        )
        return str(resp.json()["choices"][0]["message"]["content"] or "")
