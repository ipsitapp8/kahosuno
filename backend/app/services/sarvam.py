"""Async client for the Sarvam AI REST APIs (STT, translate, TTS, chat)."""

import base64
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.services.providers import ProviderError, post_with_retry

# Speaker per language for bulbul:v3. Verified against the live API for od-IN and hi-IN
# (Phase 2); the others are assumed to work the same way.
VOICES: dict[str, str] = {
    "hi-IN": "shubh",
    "kn-IN": "shubh",
    "od-IN": "priya",
    "bn-IN": "aditya",
    "en-IN": "ritu",
    "pa-IN": "rahul",
}


class SarvamError(ProviderError):
    """Raised when a Sarvam call fails after retries."""


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
        return await post_with_retry(
            self._http, path, self._headers(), self._s.sarvam_max_retries, SarvamError, **kwargs
        )

    async def speech_to_text(self, wav_bytes: bytes, lang: str) -> str:
        resp = await self._post(
            "/speech-to-text",
            files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            data={"model": self._s.stt_model, "language_code": lang},
        )
        return str(resp.json()["transcript"])

    def _mode(self) -> str:
        # sarvam-translate:v1 only supports the formal mode
        return "formal" if self._s.translate_model.startswith("sarvam-translate") else (
            self._s.translate_mode
        )

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
                "mode": self._mode(),
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
