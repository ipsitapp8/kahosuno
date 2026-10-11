from collections.abc import Iterator
from pathlib import Path

import numpy as np

from app.services.pipeline import wav_to_pcm

FIXTURES = Path(__file__).parent / "fixtures"
SILENCE_100MS = b"\x00\x00" * 1600


def speech_pcm() -> bytes:
    """Real speech (Odia, synthesised by Sarvam TTS), 16 kHz mono PCM16."""
    pcm = wav_to_pcm((FIXTURES / "odia_speech.wav").read_bytes())
    loud = np.flatnonzero(np.abs(np.frombuffer(pcm, dtype="<i2")) > 300)
    return pcm[loud[0] * 2 : (loud[-1] + 1) * 2]  # trim the TTS lead-in/tail silence


def silence(ms: int) -> bytes:
    return b"\x00\x00" * (16 * ms)


def chunks(pcm: bytes, size: int = 3200) -> Iterator[bytes]:
    for i in range(0, len(pcm), size):
        yield pcm[i : i + size]
