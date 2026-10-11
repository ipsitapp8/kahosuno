"""Real-API smoke tests and benchmarks. Run from backend/ with PYTHONPATH=. :

  python scripts/smoke.py pipeline kn-IN hi-IN [--stt gnani] [--tts gnani] [--runs 3]
  python scripts/smoke.py translate-bench

`pipeline` makes a synthetic input utterance with Sarvam TTS (independent of the providers under
test), then runs STT -> translate -> TTS and prints per-stage latency for each run. Pass
`--wav file.wav` (16 kHz mono) to use a real recording instead.
"""

import argparse
import asyncio
import statistics
import time
from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.factory import build_providers
from app.services.pipeline import (
    SAMPLE_RATE,
    AudioEvent,
    DoneEvent,
    TranscriptEvent,
    pcm_to_wav,
    wav_to_pcm,
)
from app.services.sarvam import SarvamClient

OUT = Path("out")
SENTENCES = {
    "kn-IN": [
        "ನಮಸ್ಕಾರ, ನನ್ನ ಹೆಸರು ರಮೇಶ್. ನೀವು ಹೇಗಿದ್ದೀರಾ?",
        "ನಾನು ಬೆಂಗಳೂರಿನಲ್ಲಿ ಕೆಲಸ ಮಾಡುತ್ತೇನೆ, ಈ ತಿಂಗಳು ಮನೆಗೆ ಹಣ ಕಳುಹಿಸುತ್ತೇನೆ.",
        "ಅಮ್ಮನ ಆರೋಗ್ಯ ಈಗ ಹೇಗಿದೆ? ವೈದ್ಯರು ಏನು ಹೇಳಿದರು?",
        "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಓಟಿಪಿ ಯಾರಿಗೂ ಹೇಳಬೇಡಿ.",
    ],
    "hi-IN": [
        "नमस्ते, मेरा नाम सीता है। आप कैसे हैं?",
        "मैं गाँव में हूँ, इस महीने पैसे भेज दूँगी।",
        "माँ की तबीयत अब कैसी है? डॉक्टर ने क्या कहा?",
        "कृपया अपना ओटीपी किसी को मत बताइए।",
    ],
}

async def make_input(settings: Settings, lang: str, text: str) -> bytes:
    sarvam = SarvamClient(settings)
    try:
        return wav_to_pcm(await sarvam.text_to_speech(text, lang))
    finally:
        await sarvam.aclose()

async def pipeline_cmd(args: argparse.Namespace) -> None:
    OUT.mkdir(exist_ok=True)
    settings = get_settings().model_copy(
        update={"stt_provider": args.stt, "tts_provider": args.tts}
    )
    if args.wav:
        pcm = wav_to_pcm(Path(args.wav).read_bytes())
    else:
        pcm = await make_input(settings, args.src, SENTENCES[args.src][0])
        (OUT / f"input_{args.src}.wav").write_bytes(pcm_to_wav(pcm))
    providers = build_providers(settings)
    pipeline = providers.pipeline()
    rows: list[tuple[int, int, int, int]] = []
    try:
        for run in range(args.runs):
            audio = bytearray()
            async for ev in pipeline.process(pcm, args.src, args.tgt):
                if isinstance(ev, TranscriptEvent) and run == 0:
                    print(f"[{args.src}] {ev.original}\n[{args.tgt}] {ev.translated}")
                elif isinstance(ev, AudioEvent):
                    audio += ev.pcm
                elif isinstance(ev, DoneEvent):
                    lat = ev.latency
                    rows.append((lat.stt_ms, lat.translate_ms, lat.tts_ms, lat.total_ms))
                    print(f"run {run + 1}: {lat}")
            if run == 0:
                name = f"{args.src}_to_{args.tgt}_{args.stt}-{args.tts}.wav"
                (OUT / name).write_bytes(pcm_to_wav(bytes(audio), SAMPLE_RATE))
                print(f"wrote out/{name} ({len(audio)} bytes PCM)")
            await asyncio.sleep(1)
    finally:
        await providers.aclose()
    med = [int(statistics.median(col)) for col in zip(*rows, strict=True)]
    print(f"MEDIAN stt={med[0]}ms translate={med[1]}ms tts_first_audio={med[2]}ms total={med[3]}ms")

async def bench_cmd(_: argparse.Namespace) -> None:
    base = get_settings()
    pairs = [("kn-IN", "hi-IN"), ("hi-IN", "kn-IN")]
    for model in ("mayura:v1", "sarvam-translate:v1"):
        client = SarvamClient(base.model_copy(update={"translate_model": model}))
        times: list[float] = []
        print(f"\n=== {model} ===")
        try:
            for src, tgt in pairs:
                for text in SENTENCES[src]:
                    out = ""
                    for _ in range(2):  # second run gives a warmer latency

                        t = time.perf_counter()
                        out = await client.translate(text, src, tgt)
                        dt = (time.perf_counter() - t) * 1000
                    times.append(dt)
                    print(f"{src}->{tgt} {dt:5.0f}ms | {text}\n{' ' * 24}=> {out}")
        finally:
            await client.aclose()
        print(f"median {statistics.median(times):.0f} ms, max {max(times):.0f} ms")

def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pipeline")
    p.add_argument("src")
    p.add_argument("tgt")
    p.add_argument("--stt", default="gnani")
    p.add_argument("--tts", default="gnani")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--wav")
    p.set_defaults(fn=pipeline_cmd)
    sub.add_parser("translate-bench").set_defaults(fn=bench_cmd)
    args = ap.parse_args()
    asyncio.run(args.fn(args))

main()
