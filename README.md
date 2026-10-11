# Bharat Call Assistant

**Voice powered by Gnani Prisma (STT) and Timbre (TTS).**

Do log phone call par apni-apni bhasha mein baat kar sakte hain, aur app beech mein live translate karti hai.
Pehli language pair: **Kannada (kn-IN) <-> Hindi (hi-IN)**. Saath mein ek **scam shield** jo OTP / KYC /
"digital arrest" jaise fraud calls pakad kar chetavni deta hai.

Kiske liye: pardes mein kaam karne wale mazdoor, unke parivar, aur buzurg log.

> Status: backend ke phases 1-4 ho chuke hain (translation pipeline, rooms, WebSocket, VAD, scam shield).
> Android app, Docker aur tone aage ke phases hain. Roadmap neeche hai.

## Kaise kaam karta hai

```
Speaker ka mic  -->  VAD (bolna khatam hua?)  -->  Gnani Prisma STT  -->  Sarvam translate  -->  Gnani Timbre TTS  -->  Listener ka speaker
                                                       (kn/hi text)        (hi/kn text)          (streaming audio)
```

| Step | Kaun | Kyun |
|---|---|---|
| Speech to text | **Gnani Prisma** (`api.vachana.ai/stt/v3`) | Kannada + Hindi dono support |
| Translation | Sarvam `sarvam-translate:v1` | Benchmark mein tez aur sirf target language deta hai |
| Text to speech | **Gnani Timbre v2.5** (SSE streaming) | Kannada voice Saanvi, Hindi voice Nalini |

Har stage ek provider interface ke peeche hai (`app/services/providers.py`), isliye vendor config se badal sakte hain
(`STT_PROVIDER`, `TTS_PROVIDER`, `TRANSLATE_PROVIDER`). IndicTrans2 ke liye ek stub taiyaar hai.

## Setup (backend)

```bash
cd backend
py -3.13 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env      # phir .env mein GNANI_API_KEY aur SARVAM_API_KEY daalein
.venv\Scripts\pytest        # saare tests (mocked, API key ki zaroorat nahi)
.venv\Scripts\uvicorn app.main:app --reload
```

Real API smoke test (key chahiye):

```bash
PYTHONPATH=. python scripts/smoke.py pipeline kn-IN hi-IN
PYTHONPATH=. python scripts/smoke.py pipeline hi-IN kn-IN
PYTHONPATH=. python scripts/smoke.py translate-bench
```

Protocol ki poori detail: [docs/protocol.md](docs/protocol.md).

## Privacy

Audio kabhi disk par save nahi hota. Sirf call metadata (languages, duration, latency) store hoga, aur transcript
sirf user ki permission se. Join karne ke liye consent zaroori hai.

## Roadmap

- Phase 4: scam shield (rules + LLM + hysteresis) -- done
- Phase 5: tone preservation
- Phase 6: Android app (Kotlin + Compose)
- Phase 7: Docker, security, final checklist
- Baad mein: **Odia (od-IN)**. Gnani STT abhi Odia support nahi karta; jab kare tab pair add hogi.
- Baad mein: Gnani realtime STT WebSocket (`wss://api.vachana.ai/stt/v3/stream`) aur Timbre TTS WebSocket, self-hosted IndicTrans2.

## Scam shield (Phase 4)

Do layers: (1) tez regex rules - English, Hindi, Kannada script, aur romanised Hinglish/Kanglish mein OTP, KYC, PIN/CVV,
account block, police/"digital arrest", lottery, AnyDesk/screen share, QR/UPI, courier, bijli-kat ki dhamki;
(2) ek LLM (Sarvam `sarvam-105b`) jo naye tareeke pakadta hai. Dono milkar ek risk score banate hain (40+ peela,
70+ laal) aur warning sirf **sun-ne wale** ko jaati hai, bolne wale ko nahi.

LLM optional hai: `SCAM_LLM_ENABLED=false` karo ya Sarvam credits khatam ho jaayein, to rules akele chalte rahte hain.
LLM sirf kabhi-kabhi poocha jaata hai (shak hone par ya har 6 turn mein ek baar, kam se kam 15 second ke gap par),
isliye free credits bachte hain.
