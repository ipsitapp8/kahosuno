"""Provider interfaces for the voice pipeline, plus a shared retrying POST helper.

The pipeline only knows these protocols; which vendor sits behind each one is chosen by
config (see factory.py).
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

RETRY_STATUS = {429, 502, 503, 504}


class ProviderError(Exception):
    """A vendor call failed (after retries)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class STTProvider(Protocol):
    async def speech_to_text(self, wav_bytes: bytes, lang: str) -> str: ...


class TranslateProvider(Protocol):
    async def translate(self, text: str, src: str, tgt: str) -> str: ...


class TTSProvider(Protocol):
    def text_to_speech_stream(
        self,
        text: str,
        lang: str,
        pace: float | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[bytes]:
        """Yield raw 16 kHz mono PCM16 chunks as they are synthesised."""
        ...


async def post_with_retry(
    http: httpx.AsyncClient,
    path: str,
    headers: dict[str, str],
    retries: int,
    err: type[ProviderError] = ProviderError,
    **kwargs: Any,
) -> httpx.Response:
    """POST with exponential backoff on 429/5xx and network errors."""
    attempts = retries + 1
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = await http.post(path, headers=headers, **kwargs)
        except httpx.TransportError as exc:
            last = exc
        else:
            if resp.status_code not in RETRY_STATUS:
                if resp.is_error:
                    raise err(
                        f"{path} failed: {resp.status_code} {resp.text[:200]}", resp.status_code
                    )
                return resp
            last = err(f"{path} returned {resp.status_code}", resp.status_code)
        if attempt < attempts - 1:
            await asyncio.sleep(0.4 * 2**attempt)
    if isinstance(last, ProviderError):
        raise last
    raise err(f"{path} failed: {last!r}")
