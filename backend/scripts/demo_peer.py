"""Play the other person on a KahoSuno call, from the keyboard.

Join a room that someone opened in the app, then type a line: it is turned into speech with
Sarvam TTS and sent into the call exactly like a microphone would. What the other side says
back, and any scam warning, is printed here.

    cd backend
    PYTHONPATH=. .venv/Scripts/python scripts/demo_peer.py 123456            # Hindi speaker
    PYTHONPATH=. .venv/Scripts/python scripts/demo_peer.py 123456 --lang kn-IN --name Ramesh

Shortcuts (Hindi): /greet  /family  /scam  /bye.  Anything else is spoken as typed.
"""

import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request

import websockets

from app.services.pipeline import wav_to_pcm
from app.services.sarvam import SarvamClient

FRAME = 3200  # 100 ms of 16 kHz mono PCM16
SHORTCUTS = {
    "/greet": "नमस्ते, मेरा नाम सीता है। आप कैसे हैं?",
    "/family": "माँ की तबीयत अब कैसी है? डॉक्टर ने क्या कहा?",
    "/scam": "मैं बैंक से बोल रहा हूँ, आपका केवाईसी अपडेट नहीं हुआ, तुरंत अपना ओटीपी बताइए।",
}


def post(server: str, path: str, body: dict[str, object]) -> dict[str, str]:
    req = urllib.request.Request(
        server + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data: dict[str, str] = json.load(resp)
            return data
    except urllib.error.HTTPError as exc:
        detail = json.loads(exc.read() or b"{}").get("detail", {})
        sys.exit(f"Could not join: {detail.get('message', exc.reason)}")


async def say(ws: websockets.ClientConnection, tts: SarvamClient, text: str, lang: str) -> None:
    pcm = wav_to_pcm(await tts.text_to_speech(text, lang))
    audio = pcm + b"\x00" * 32000 * 2  # two seconds of silence so the server hears the end
    for i in range(0, len(audio), FRAME):
        await ws.send(b"\x01" + audio[i : i + FRAME])
        await asyncio.sleep(0.02)


async def listen(ws: websockets.ClientConnection) -> None:
    async for message in ws:
        if isinstance(message, bytes):
            continue
        msg = json.loads(message)
        kind = msg["type"]
        if kind == "transcript":
            who = "you said" if msg["speaker"] == "self" else "they said"
            print(f"  [{who}] {msg['translated']}   (original: {msg['original']})", flush=True)
        elif kind == "latency":
            print(f"  [delay] {msg['total_ms']} ms", flush=True)
        elif kind == "scam_alert":
            print(
                f"  [SCAM {msg['level'].upper()}] {' | '.join(msg['reasons_hinglish'])}", flush=True
            )
        elif kind == "peer_joined":
            print(f"  [{msg['name']} joined]", flush=True)
        elif kind == "peer_left":
            print(f"  [{msg['name']} left]", flush=True)
        elif kind == "error":
            print(f"  [error] {msg['code']}: {msg['message']}", flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("code", help="the 6 digit room code shown in the app")
    ap.add_argument("--name", default="Sita")
    ap.add_argument("--lang", default="hi-IN", help="language you speak (default hi-IN)")
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    ticket = post(
        args.server,
        f"/rooms/{args.code}/join",
        {"name": args.name, "language": args.lang, "consent": True},
    )
    ws_url = args.server.replace("http", "ws", 1) + f"/ws/v1/rooms/{ticket['room_id']}"
    tts = SarvamClient()
    loop = asyncio.get_running_loop()
    async with websockets.connect(f"{ws_url}?token={ticket['token']}") as ws:
        hello = {"v": 1, "type": "hello", "name": args.name, "language": args.lang, "consent": True}
        await ws.send(json.dumps(hello))
        listener = asyncio.create_task(listen(ws))
        print(f"Joined room {args.code} as {args.name} ({args.lang}). Type a line to speak it.")
        print("Shortcuts: /greet /family /scam /bye", flush=True)
        try:
            while True:
                raw = await loop.run_in_executor(None, sys.stdin.readline)
                if raw == "":  # end of input
                    break
                line = raw.strip()
                if not line:
                    continue
                if line == "/bye":
                    await ws.send(json.dumps({"v": 1, "type": "bye"}))
                    break
                text = SHORTCUTS.get(line, line)
                print(f"  [speaking] {text}", flush=True)
                await say(ws, tts, text, args.lang)
        finally:
            listener.cancel()
            await tts.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
