"""Gnani AI voice providers: Prisma (STT) and Timbre (TTS), via api.vachana.ai."""

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.services.providers import ProviderError, post_with_retry

# Languages Prisma STT accepts (Odia is not supported).
STT_LANGUAGES = frozenset(
    {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"}
)

# One default Timbre v2.5 voice per language (each voice has one preferred language).
VOICES: dict[str, str] = {
    "hi-IN": "Nalini",
    "kn-IN": "Saanvi",
    "en-IN": "Kaveri",
    "bn-IN": "Kirra",
    "pa-IN": "Mehuli",
    "ta-IN": "Asmita",
    "te-IN": "Suhana",
    "ml-IN": "Reshma",
    "mr-IN": "Zahira",
    "gu-IN": "Falak",
}

SPEED_MIN, SPEED_MAX = 0.85, 1.15
SAMPLE_RATE = 16000


class GnaniError(ProviderError):
    """Raised when a Gnani call fails after retries."""


def _speed(pace: float | None) -> float:
    return min(SPEED_MAX, max(SPEED_MIN, pace)) if pace else 1.0


class GnaniClient:
    """Implements STTProvider (Prisma) and TTSProvider (Timbre)."""

    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._s = settings or get_settings()
        self._http = httpx.AsyncClient(
            base_url=self._s.gnani_base_url,
            timeout=httpx.Timeout(self._s.gnani_timeout_s),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        key = self._s.gnani_api_key.get_secret_value()
        if not key:
            raise GnaniError("GNANI_API_KEY is not set")
        return {"X-API-Key-ID": key}

    # ---- Prisma STT ----
    async def speech_to_text(self, wav_bytes: bytes, lang: str) -> str:
        if lang not in STT_LANGUAGES:
            raise GnaniError(f"Gnani STT does not support {lang}")
        resp = await post_with_retry(
            self._http,
            "/stt/v3",
            self._headers(),
            self._s.gnani_max_retries,
            GnaniError,
            files={"audio_file": ("audio.wav", wav_bytes, "audio/wav")},
            data={"language_code": lang, "format": self._s.gnani_stt_format},
        )
        return str(resp.json()["transcript"])

    # ---- Timbre TTS ----
    def _tts_body(self, text: str, lang: str, pace: float | None) -> dict[str, Any]:
        voice = VOICES.get(lang)
        if voice is None:
            raise GnaniError(f"No Gnani voice configured for {lang}")
        return {
            "text": text,
            "model": self._s.gnani_tts_model,
            "voice": voice,
            "language": lang,
            "speed": _speed(pace),
            "audio_config": {
                "sample_rate": SAMPLE_RATE,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "pcm_s16le",
                "container": "raw",
            },
        }

    async def text_to_speech(self, text: str, lang: str, pace: float | None = None) -> bytes:
        """REST synthesis. Returns raw 16 kHz PCM16 (the whole utterance)."""
        resp = await post_with_retry(
            self._http,
            "/api/v1/tts/inference",
            self._headers(),
            self._s.gnani_max_retries,
            GnaniError,
            json=self._tts_body(text, lang, pace),
        )
        return resp.content

    async def text_to_speech_stream(
        self,
        text: str,
        lang: str,
        pace: float | None = None,
        temperature: float | None = None,  # Timbre has no temperature control
    ) -> AsyncIterator[bytes]:
        """SSE streaming synthesis: yields raw PCM16 chunks as they are generated."""
        async with self._http.stream(
            "POST",
            "/api/v1/tts/sse",
            headers=self._headers(),
            json=self._tts_body(text, lang, pace),
        ) as resp:
            if resp.is_error:
                detail = (await resp.aread()).decode(errors="replace")[:200]
                raise GnaniError(
                    f"tts stream failed: {resp.status_code} {detail}", resp.status_code
                )
            event = ""
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    payload = line[5:].strip()
                    if not payload:
                        continue
                    data = json.loads(payload)
                    if event == "error":
                        raise GnaniError(f"tts stream error: {payload[:200]}")
                    audio = data.get("audio")
                    if event == "chunk" and audio:
                        yield base64.b64decode(audio)
                    elif event == "complete" or data.get("is_final"):
                        return
