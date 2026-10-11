from app.services.vad import FRAME_BYTES, Segmenter
from tests.helpers import chunks, silence, speech_pcm


class AlwaysSpeech:
    def is_speech(self, frame: bytes) -> bool:
        return True


def run(seg: Segmenter, pcm: bytes, size: int = 3200) -> list[bytes]:
    out: list[bytes] = []
    for c in chunks(pcm, size):
        out += seg.feed(c)
    return out


def test_one_utterance_from_real_speech() -> None:
    speech = speech_pcm()
    utts = run(Segmenter(), silence(1000) + speech + silence(1000))
    assert len(utts) == 1
    # The utterance covers the speech (within a frame or two of tolerance).
    assert len(utts[0]) >= len(speech) * 0.9
    assert len(utts[0]) <= len(speech) + silence(1000).__len__()


def test_two_utterances_split_by_silence() -> None:
    speech = speech_pcm()
    pcm = silence(500) + speech + silence(1200) + speech + silence(1000)
    assert len(run(Segmenter(), pcm)) == 2


def test_short_pause_does_not_split() -> None:
    speech = speech_pcm()
    pcm = silence(300) + speech + silence(200) + speech + silence(1000)
    assert len(run(Segmenter(), pcm)) == 1


def test_silence_yields_nothing() -> None:
    assert run(Segmenter(), silence(3000)) == []


def test_chunk_size_does_not_matter() -> None:
    pcm = silence(500) + speech_pcm() + silence(1000)
    a = run(Segmenter(), pcm, 3200)
    b = run(Segmenter(), pcm, 1000)  # odd size, not frame aligned
    assert a == b


def test_max_length_cut() -> None:
    seg = Segmenter(detector=AlwaysSpeech(), max_ms=1000)
    utts = run(seg, silence(3100))
    assert len(utts) == 3
    assert all(len(u) == 1000 // 20 * FRAME_BYTES for u in utts)


def test_noise_blip_below_min_speech_is_dropped() -> None:
    class Blip:
        def __init__(self) -> None:
            self.n = 0

        def is_speech(self, frame: bytes) -> bool:
            self.n += 1
            return self.n == 5  # a single speech frame (20 ms)

    assert run(Segmenter(detector=Blip()), silence(2000)) == []


def test_flush_ends_open_utterance() -> None:
    seg = Segmenter(detector=AlwaysSpeech())
    seg.feed(silence(600))
    assert seg.flush() is not None
    assert seg.flush() is None
