# Pitch notes: Gnani AI "Great Indian AI Internship Challenge" (deadline 10 Nov 2026)

## One line
Bharat Call Assistant lets a Kannada speaker and a Hindi speaker talk on a normal-feeling call, with live
translation and a scam shield. **Voice powered by Gnani Prisma (STT) and Timbre (TTS).**

## Problem
Lakhs of migrant workers from one state work in another, and their families and elders cannot speak the local
language. The same people are the most exposed to phone fraud (OTP, KYC, digital arrest).

## What Gnani powers
- **Prisma STT** hears the speaker in Kannada or Hindi (`/stt/v3`).
- **Timbre v2.5 TTS** speaks the translation in the listener's language, streamed over SSE so audio starts before
  synthesis finishes.
- Both sit behind provider interfaces, so Gnani realtime WebSocket STT/TTS is the planned next step.

## Honest numbers
See the latency table in `docs/benchmarks.md` (filled from real runs). Target: under 2.5 s from end of speech
to first audio.

## Design choices worth saying out loud
- Odia is on the roadmap, not in the demo: Gnani STT does not support Odia yet, so we moved the first pair to
  Kannada <-> Hindi instead of faking it.
- Translation uses Sarvam `sarvam-translate:v1`. In our 8-sentence benchmark it was faster than `mayura:v1` and,
  unlike mayura, did not mix English words into the output, which matters when a TTS voice reads it aloud.
- Privacy first: no audio stored, transcripts opt-in, consent required to join.

## Demo script (2 minutes)
1. Two phones join one room, Kannada and Hindi.
2. Kannada speaker talks; Hindi listener hears Hindi with the on-screen transcript and latency.
3. A "bank officer" speaker says "OTP batao, warna account block" and the scam banner fires.
