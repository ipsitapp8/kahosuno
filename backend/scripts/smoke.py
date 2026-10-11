"""Real-API smoke test. Run from backend/:  .venv/Scripts/python scripts/smoke.py [odia.wav]

1. Probes which TTS speakers work per model/language (writes nothing but a report).
2. Takes an Odia WAV (16 kHz mono) or synthesises one, runs the pipeline od-IN -> hi-IN,
   prints stage latency and writes out/hindi.wav.
"""

import asyncio
import sys
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.services.pipeline import (
    SAMPLE_RATE,
    AudioEvent,
    DoneEvent,
    TranscriptEvent,
    TranslationPipeline,
    pcm_to_wav,
    wav_to_pcm,
)
from app.services.sarvam import VOICES, SarvamClient

CANDIDATES = ["shubh", "priya", "aditya", "ritu", "rahul", "ishita", "roopa", "simran", "varun"]
MODELS = ["bulbul:v3", "bulbul:v4-flash"]
LANGS = ["od-IN", "hi-IN"]
SAMPLE_TEXT = {"od-IN": "ନମସ୍କାର, ମୋର ନାମ ରମେଶ। ଆପଣ କେମିତି ଅଛନ୍ତି?", "hi-IN": "नमस्ते, आप कैसे हैं?"}
OUT = Path("out")


async def probe_voices() -> dict[tuple[str, str], list[str]]:
    s = get_settings()
    ok: dict[tuple[str, str], list[str]] = {}
    async with httpx.AsyncClient(base_url=s.sarvam_base_url, timeout=30) as http:
        for model in MODELS:
            for lang in LANGS:
                for speaker in CANDIDATES:
                    r = await http.post(
                        "/text-to-speech",
                        headers={"api-subscription-key": s.sarvam_api_key.get_secret_value()},
                        json={"text": SAMPLE_TEXT[lang], "language_code": lang,
                              "model": model, "speaker": speaker, "speech_sample_rate": 16000},
                    )
                    if r.status_code == 200:
                        ok.setdefault((model, lang), []).append(speaker)
                    await asyncio.sleep(2.1)  # stay under 30 req/min on Starter
                print(model, lang, "->", ok.get((model, lang), []), flush=True)
    return ok


async def run_pipeline(client: SarvamClient, wav_path: str | None) -> None:
    OUT.mkdir(exist_ok=True)
    if wav_path:
        pcm = wav_to_pcm(Path(wav_path).read_bytes())
    else:
        print("No WAV given: synthesising Odia speech with TTS")
        pcm = wav_to_pcm(await client.text_to_speech(SAMPLE_TEXT["od-IN"], "od-IN"))
        (OUT / "odia_input.wav").write_bytes(pcm_to_wav(pcm))
    audio = bytearray()
    async for ev in TranslationPipeline(client).process(pcm, "od-IN", "hi-IN"):
        if isinstance(ev, TranscriptEvent):
            print(f"odia : {ev.original}\nhindi: {ev.translated}")
        elif isinstance(ev, AudioEvent):
            audio += ev.pcm
        elif isinstance(ev, DoneEvent):
            print("latency:", ev.latency)
    (OUT / "hindi.wav").write_bytes(pcm_to_wav(bytes(audio), SAMPLE_RATE))
    print(f"wrote out/hindi.wav ({len(audio)} bytes PCM)")


async def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("voices", "all"):
        await probe_voices()
    if mode in ("pipeline", "all"):
        client = SarvamClient()
        try:
            await run_pipeline(client, sys.argv[2] if len(sys.argv) > 2 else None)
        finally:
            await client.aclose()
    print("configured VOICES:", VOICES)


asyncio.run(main())
