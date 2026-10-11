"""Utterance pipeline: STT -> translate -> streamed TTS, with per-stage latency."""

import io
import re
import time
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.services.providers import STTProvider, TranslateProvider, TTSProvider

SAMPLE_RATE = 16000
MAX_TRANSLATE_CHARS = 900  # mayura:v1 limit is 1000
_SENTENCE_END = re.compile(r"(?<=[.!?।॥])\s+")


@dataclass(frozen=True)
class Latency:
    stt_ms: int
    translate_ms: int
    tts_ms: int  # time from end of translate to first audio chunk
    total_ms: int  # end of speech to first audio chunk


@dataclass(frozen=True)
class TranscriptEvent:
    original: str
    translated: str
    stt_ms: int
    translate_ms: int


@dataclass(frozen=True)
class AudioEvent:
    pcm: bytes


@dataclass(frozen=True)
class DoneEvent:
    latency: Latency


PipelineEvent = TranscriptEvent | AudioEvent | DoneEvent


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def wav_to_pcm(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return w.readframes(w.getnframes())


def split_text(text: str, max_chars: int = MAX_TRANSLATE_CHARS) -> list[str]:
    """Split on sentence ends, then pack into pieces of at most max_chars."""
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text.strip()):
        while len(sentence) > max_chars:  # no punctuation: cut at the last space
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            head, sentence = sentence[:cut], sentence[cut:].lstrip()
            if current:
                pieces.append(current)
                current = ""
            pieces.append(head)
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return [p for p in pieces if p]


def _ms(start: float, end: float) -> int:
    return round((end - start) * 1000)


class TranslationPipeline:
    def __init__(self, stt: STTProvider, translate: TranslateProvider, tts: TTSProvider) -> None:
        self._stt = stt
        self._translate = translate
        self._tts = tts

    async def process(
        self,
        pcm: bytes,
        src: str,
        tgt: str,
        pace: float | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[PipelineEvent]:
        """Run one utterance (16 kHz mono PCM16). Yields the transcript first, then
        audio chunks as they arrive, then the final latency. `t0` is end of speech."""
        t0 = time.perf_counter()
        original = await self._stt.speech_to_text(pcm_to_wav(pcm), src)
        t_stt = time.perf_counter()

        translated = " ".join(
            [await self._translate.translate(part, src, tgt) for part in split_text(original)]
        )
        t_tr = time.perf_counter()
        yield TranscriptEvent(original, translated, _ms(t0, t_stt), _ms(t_stt, t_tr))

        if not translated.strip():  # silence or noise: nothing to speak
            yield DoneEvent(Latency(_ms(t0, t_stt), _ms(t_stt, t_tr), 0, _ms(t0, t_tr)))
            return

        first_audio: float | None = None
        for part in split_text(translated, 2500):
            async for chunk in self._tts.text_to_speech_stream(part, tgt, pace, temperature):
                if first_audio is None:
                    first_audio = time.perf_counter()
                yield AudioEvent(chunk)
        end = first_audio if first_audio is not None else time.perf_counter()
        yield DoneEvent(Latency(_ms(t0, t_stt), _ms(t_stt, t_tr), _ms(t_tr, end), _ms(t0, end)))
