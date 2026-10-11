# Benchmarks (real API runs, 2026-10-11)

Latency = end of speech to each stage finishing. `tts` is time from translation done to the **first audio
chunk**. Median of 3 runs. Input is synthetic speech made with Sarvam TTS (kn: 3.75 s, hi: 2.56 s), one
sentence each, so these are best-case numbers on clean audio, not phone-line audio. Translation model:
`sarvam-translate:v1` for every row except the first.

| Run | STT | Translate | TTS first audio | **Total** |
|---|---|---|---|---|
| Phase 2: Sarvam voice, od -> hi (`mayura:v1`) | 292 ms | 1237 ms | 294 ms | 1824 ms |
| Sarvam voice, kn -> hi | 249 ms | 1101 ms | 211 ms | **1559 ms** |
| Sarvam voice, hi -> kn | 268 ms | 1127 ms | 216 ms | **1611 ms** |
| **Gnani Prisma + Timbre, kn -> hi** | 476 ms | 1141 ms | 240 ms | **1931 ms** |
| **Gnani Prisma + Timbre, hi -> kn** | 260 ms | 1128 ms | 234 ms | **1637 ms** |

All rows are under the 2.5 s target.

## Reading the numbers
- **Translation is about 60-70% of the total** whichever vendor does the voice. It is the best place to
  win latency (self-hosted IndicTrans2 is the planned option).
- **Gnani TTS** time to first audio (234-240 ms) is on par with Sarvam (211-216 ms). The SSE stream sends
  4096-byte chunks (128 ms of audio), raw PCM with no WAV header, so playback can start immediately.
- **Gnani STT** hi -> kn (260 ms) matches Sarvam (268 ms). kn -> hi was slower (476 ms), but that clip is also
  46% longer (3.75 s vs 2.56 s), and STT time grows with audio length. This is not a controlled comparison,
  so treat "Gnani STT is slower on Kannada" as unproven until tested with the same real recordings.
- Gnani STT returns Kannada text without punctuation; with `format=transcribe` the translation was still correct.

## Translation model choice (4 sentences x 2 directions, 2 runs each)
| Model | Median | Output quality |
|---|---|---|
| `mayura:v1` (modern-colloquial) | 1222 ms | Mixes English words in ("Mother की health", "country-ಯಲ್ಲಿ"), mistranslated "गाँव" as "country" |
| `sarvam-translate:v1` | **1125 ms** | Pure target language, correct on all 8 |

Chosen: `sarvam-translate:v1`. English-mixed text is also a poor fit for a TTS voice that reads one language.

## Caveats
- Single machine, home network, no load. One speaker per language.
- Not yet measured: real recordings, noisy audio, long utterances, realtime STT WebSocket.
- Reproduce: `PYTHONPATH=. python scripts/smoke.py pipeline kn-IN hi-IN --stt gnani --tts gnani` (and
  `--stt sarvam --tts sarvam`), and `python scripts/smoke.py translate-bench`.
