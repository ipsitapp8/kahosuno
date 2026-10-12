# Final end-to-end checklist

`[x]` = I ran it and saw it work. `[ ]` = not done or not verified. Dates are 2026-10-12.

## Backend
- [x] `ruff`, `mypy` clean; **198 tests pass** (`cd backend && pytest`)
- [x] Docker image builds; container runs as a non-root user and reports **healthy**
- [x] Real two-way call against the **container** with live Gnani + Sarvam: Kannada -> Hindi 1.9 s, Hindi -> Kannada 1.7 s, speech audio both ways
- [x] `APP_ENV=production` **refuses to start** with a weak `JWT_SECRET` (checked in the container)
- [x] Join tokens are **redacted from logs** (container log: 0 raw tokens, `token=<redacted>`)
- [x] No log line contains what was said (container log checked; also a test)
- [x] Database holds numbers only; transcript lines only for the speaker who opted in (checked in the container)
- [x] Security headers, rate limits (per IP), room cap, frame-size limits, uvicorn websocket size limit in the Docker `CMD`
- [x] `docker-compose.yml` and `render.yaml` parse and validate (`docker compose config`)
- [x] `docker compose up --build` starts the backend and it reports healthy; a 100 KB websocket frame is refused (close code 1009)
- [ ] Deployed on Render and called from the emulator over `https`/`wss`
- [x] GitHub Actions: backend (ruff, mypy, 198 tests), Docker (build + /health) and Android (assembleDebug + 81 tests) all pass on GitHub's runners

## Android
- [x] `assembleDebug` builds; **81 unit tests pass** through Android Gradle
- [x] Installed and run on an emulator ("Medium Phone", API 37): join form, permissions, foreground service + notification
- [x] Real call: peer's Hindi arrives as large Kannada text with the original small, delay chip, tone chip, timer
- [x] Scam banner: yellow and red, Hinglish reasons, **Call kaato** hangs up at once, service stops
- [x] History shows metadata only; name and language remembered
- [x] Dead room / server restart shows a clear "call ended" screen
- [ ] **Speaking into the app** (emulator microphone is silent unless the host mic is switched on)
- [ ] **Hearing** the translated voice (playback runs, but I cannot listen)
- [ ] Real phone, real network, Bluetooth headset, screen-off call, vibration strength
- [ ] Hindi and Kannada UI strings reviewed by a native speaker
- [ ] Server error text on the "call ended" screen is English (not localized yet)

## Voice and language
- [x] Gnani Prisma (STT) and Timbre (TTS) in the loop; Sarvam only for translation and the scam LLM
- [x] Kannada <-> Hindi works on synthetic speech
- [ ] Tested on **real recordings** (phone-line noise, accents, long sentences)
- [ ] Odia (roadmap: Gnani STT does not support it yet)

## Scam shield
- [x] 37 scam + 30 normal sentences in English, Hindi, Kannada, Hinglish, Kanglish, including spelled-out acronyms ("ओ टी पी")
- [x] LLM layer optional (`SCAM_LLM_ENABLED=false`), falls back to rules on any failure, call budget capped
- [ ] Measured on **real scam call transcripts** (only hand-written and synthetic samples so far)

## Not built yet
- [ ] Tone preservation (Phase 5)
- [ ] Gnani realtime STT/TTS WebSockets (REST + SSE used today)
- [ ] Self-hosted IndicTrans2 (stub only)
- [ ] Demo video
