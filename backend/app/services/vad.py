"""Voice-activity segmentation of a 16 kHz mono PCM16 stream into utterances."""

from collections import deque
from typing import Protocol

import webrtcvad

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * 2  # 640


class SpeechDetector(Protocol):
    def is_speech(self, frame: bytes) -> bool: ...


class WebRtcDetector:
    def __init__(self, aggressiveness: int = 2) -> None:
        self._vad = webrtcvad.Vad(aggressiveness)

    def is_speech(self, frame: bytes) -> bool:
        return bool(self._vad.is_speech(frame, SAMPLE_RATE))


class Segmenter:
    """Feed arbitrary-sized PCM chunks; get back finished utterances (PCM bytes).

    An utterance starts at the first speech frame (with a short pre-roll), ends after
    `hangover_ms` of silence, and is cut at `max_ms` so it stays under the STT limit.
    Utterances with less than `min_speech_ms` of speech are discarded as noise.
    """

    def __init__(
        self,
        detector: SpeechDetector | None = None,
        hangover_ms: int = 500,
        min_speech_ms: int = 250,
        preroll_ms: int = 200,
        max_ms: int = 25000,
    ) -> None:
        self._det = detector or WebRtcDetector()
        self._hangover = hangover_ms // FRAME_MS
        self._min_speech = min_speech_ms // FRAME_MS
        self._max_frames = max_ms // FRAME_MS
        self._preroll: deque[bytes] = deque(maxlen=preroll_ms // FRAME_MS)
        self._pending = bytearray()
        self._frames: list[bytes] = []
        self._in_speech = False
        self._speech_frames = 0
        self._silence = 0

    def reset(self) -> None:
        self._preroll.clear()
        self._pending.clear()
        self._reset_utterance()

    def _reset_utterance(self) -> None:
        self._frames = []
        self._in_speech = False
        self._speech_frames = 0
        self._silence = 0

    def _finish(self) -> bytes | None:
        out = b"".join(self._frames) if self._speech_frames >= self._min_speech else None
        self._reset_utterance()
        return out

    def feed(self, pcm: bytes) -> list[bytes]:
        self._pending += pcm
        done: list[bytes] = []
        while len(self._pending) >= FRAME_BYTES:
            frame = bytes(self._pending[:FRAME_BYTES])
            del self._pending[:FRAME_BYTES]
            speech = self._det.is_speech(frame)
            if not self._in_speech:
                if not speech:
                    self._preroll.append(frame)
                    continue
                self._in_speech = True
                self._frames = [*self._preroll, frame]
                self._preroll.clear()
                self._speech_frames = 1
                continue
            self._frames.append(frame)
            if speech:
                self._speech_frames += 1
                self._silence = 0
            else:
                self._silence += 1
            if self._silence >= self._hangover or len(self._frames) >= self._max_frames:
                utt = self._finish()
                if utt:
                    done.append(utt)
        return done

    def flush(self) -> bytes | None:
        """End the current utterance now (e.g. the stream stopped)."""
        return self._finish() if self._in_speech else None
