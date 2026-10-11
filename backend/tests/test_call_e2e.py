"""End-to-end calls: two fake websocket clients, real VAD, real speech fixture, fake Sarvam."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from tests.conftest import FakePipeline
from tests.helpers import chunks, silence, speech_pcm

OD = {"name": "Ramesh", "language": "kn-IN", "consent": True}
HI = {"name": "Sita", "language": "hi-IN", "consent": True}

Msg = dict[str, Any] | bytes


def open_room(client: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    a = client.post("/rooms", json=OD).json()
    b = client.post(f"/rooms/{a['code']}/join", json=HI).json()
    return a, b


def url(info: dict[str, str]) -> str:
    return f"/ws/v1/rooms/{info['room_id']}?token={info['token']}"


def hello(ws: WebSocketTestSession, who: dict[str, Any], **extra: Any) -> None:
    ws.send_json({"v": 1, "type": "hello", **who, **extra})


def recv(ws: WebSocketTestSession) -> Msg:
    m = ws.receive()
    if m.get("text") is not None:
        data: dict[str, Any] = json.loads(m["text"])
        return data
    return bytes(m["bytes"])


def collect_until(ws: WebSocketTestSession, stop: str) -> list[Msg]:
    out: list[Msg] = []
    while True:
        m = recv(ws)
        out.append(m)
        if isinstance(m, dict) and m["type"] == stop:
            return out


def types(msgs: list[Msg]) -> list[str]:
    return [m["type"] if isinstance(m, dict) else f"audio:{m[0]:#x}" for m in msgs]


def speak(ws: WebSocketTestSession, pcm: bytes) -> None:
    for c in chunks(silence(300) + pcm + silence(1000)):
        ws.send_bytes(b"\x01" + c)


def sync(ws: WebSocketTestSession) -> list[Msg]:
    """Round-trip a ping so everything sent before it has been handled."""
    ws.send_json({"v": 1, "type": "ping"})
    return collect_until(ws, "pong")


def join_both(
    client: TestClient, wa: WebSocketTestSession, wb: WebSocketTestSession,
    a: dict[str, str], b: dict[str, str], **extra: Any,
) -> None:
    hello(wa, OD, **extra)
    assert recv(wa)["type"] == "joined"  # type: ignore[call-overload]
    hello(wb, HI, **extra)
    joined = recv(wb)
    assert isinstance(joined, dict) and joined["peer"] == {"name": "Ramesh", "language": "kn-IN"}
    assert recv(wa)["type"] == "peer_joined"  # type: ignore[call-overload]


def test_full_two_way_call(client: TestClient, pipeline: FakePipeline) -> None:
    a, b = open_room(client)
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        join_both(client, wa, wb, a, b)

        speak(wa, speech_pcm())  # Kannada speaker talks, VAD finds the utterance by itself
        heard = collect_until(wb, "latency")
        assert types(heard) == [
            "transcript", "tts_start", "audio:0x2", "audio:0x2", "tts_end", "latency",
        ]
        first = heard[0]
        assert isinstance(first, dict) and first["speaker"] == "peer"
        assert first["translated"] == "नमस्ते"
        said = collect_until(wa, "latency")
        assert types(said) == ["transcript", "latency"]
        assert said[0]["speaker"] == "self"  # type: ignore[call-overload]
        assert said[1]["total_ms"] == 40  # type: ignore[call-overload]

        speak(wb, speech_pcm())  # and the reply goes the other way
        reply = collect_until(wa, "latency")
        assert "audio:0x2" in types(reply)
        collect_until(wb, "latency")

    assert [(c[1], c[2]) for c in pipeline.calls] == [("kn-IN", "hi-IN"), ("hi-IN", "kn-IN")]
    assert all(c[0] > 16000 for c in pipeline.calls)  # about a second of speech or more
    m = client.get("/metrics").json()
    assert m["utterances"] == 2
    assert m["latency"]["total_ms"]["p50"] == 40


def test_push_to_talk(client: TestClient, pipeline: FakePipeline) -> None:
    a, b = open_room(client)
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        join_both(client, wa, wb, a, b, mode="ptt")
        speak(wa, speech_pcm())  # not holding the button: ignored
        sync(wa)
        assert pipeline.calls == []

        wa.send_json({"v": 1, "type": "ptt_start"})
        for c in chunks(speech_pcm()):
            wa.send_bytes(b"\x01" + c)
        wa.send_json({"v": 1, "type": "ptt_end"})
        assert "transcript" in types(collect_until(wb, "latency"))
        assert len(pipeline.calls) == 1


def test_consent_required(client: TestClient) -> None:
    a, _ = open_room(client)
    with client.websocket_connect(url(a)) as wa:
        hello(wa, OD, consent=False)
        err = recv(wa)
        assert isinstance(err, dict)
        assert err["code"] == "consent_required" and err["fatal"] is True


def test_bad_token_and_unknown_room(client: TestClient) -> None:
    a, _ = open_room(client)
    with client.websocket_connect(f"/ws/v1/rooms/{a['room_id']}?token=garbage") as ws:
        assert recv(ws)["code"] == "bad_token"  # type: ignore[call-overload]
    with client.websocket_connect(f"/ws/v1/rooms/deadbeef?token={a['token']}") as ws:
        assert recv(ws)["code"] == "room_not_found"  # type: ignore[call-overload]


def test_errors_never_end_the_call(client: TestClient, pipeline: FakePipeline) -> None:
    a, b = open_room(client)
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        wa.send_bytes(b"\x01" + b"\x00" * 3200)  # audio before hello
        assert recv(wa)["code"] == "bad_message"  # type: ignore[call-overload]
        hello(wa, OD)
        recv(wa)
        hello(wb, HI)
        recv(wb)
        recv(wa)  # peer_joined

        wa.send_bytes(b"\x01" + b"\x00" * 20000)
        assert recv(wa)["code"] == "frame_too_large"  # type: ignore[call-overload]
        wa.send_bytes(b"\x07" + b"\x00" * 640)
        assert recv(wa)["code"] == "bad_message"  # type: ignore[call-overload]
        wa.send_text("{not json")
        assert recv(wa)["code"] == "bad_message"  # type: ignore[call-overload]

        pipeline.fail = True  # Sarvam outage: the speaker gets an error, call stays up
        speak(wa, speech_pcm())
        err = collect_until(wa, "error")[-1]
        assert isinstance(err, dict)
        assert err["code"] == "upstream_failed" and err["fatal"] is False

        pipeline.fail = False  # and it recovers on the next utterance
        speak(wa, speech_pcm())
        assert "transcript" in types(collect_until(wb, "latency"))
        assert client.get("/metrics").json()["errors"] == 1


def test_speaking_alone_is_dropped(client: TestClient, pipeline: FakePipeline) -> None:
    a, _ = open_room(client)
    with client.websocket_connect(url(a)) as wa:
        hello(wa, OD)
        recv(wa)
        speak(wa, speech_pcm())
        sync(wa)
        assert pipeline.calls == []


def test_silence_noise_is_not_translated(client: TestClient, pipeline: FakePipeline) -> None:
    a, b = open_room(client)
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        join_both(client, wa, wb, a, b)
        speak(wa, silence(2000))
        sync(wa)
        assert pipeline.calls == []


def test_reconnect_within_grace_keeps_slot(client: TestClient) -> None:
    a, b = open_room(client)
    with client.websocket_connect(url(b)) as wb:
        with client.websocket_connect(url(a)) as wa:
            join_both(client, wa, wb, a, b)
        with client.websocket_connect(url(a)) as wa2:  # same token, straight back
            hello(wa2, OD)
            joined = recv(wa2)
            assert isinstance(joined, dict) and joined["peer"]["name"] == "Sita"
            assert "peer_left" not in types(sync(wb))


def test_peer_left_after_grace(client: TestClient) -> None:
    a, b = open_room(client)
    with client.websocket_connect(url(b)) as wb:
        with client.websocket_connect(url(a)) as wa:
            join_both(client, wa, wb, a, b)
        left = collect_until(wb, "peer_left")[-1]  # grace is 0.3 s in tests
        assert isinstance(left, dict) and left["name"] == "Ramesh"


@pytest.mark.parametrize("mode", ["auto", "ptt"])
def test_mode_switch_mid_call(client: TestClient, pipeline: FakePipeline, mode: str) -> None:
    a, b = open_room(client)
    other = "ptt" if mode == "auto" else "auto"
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        join_both(client, wa, wb, a, b, mode=other)
        wa.send_json({"v": 1, "type": "mode", "mode": mode})
        if mode == "auto":
            speak(wa, speech_pcm())
            assert "transcript" in types(collect_until(wb, "latency"))
        else:
            speak(wa, speech_pcm())
            sync(wa)
            assert pipeline.calls == []


def test_bye_leaves_immediately_but_a_dropped_connection_gets_grace() -> None:
    """A deliberate hang-up must not make the other person wait out the reconnect window."""
    from app.main import create_app
    from tests.conftest import FakePipeline, make_settings

    app = create_app(make_settings(reconnect_grace_s=60.0), FakePipeline())  # a very long grace
    with TestClient(app) as client:
        a, b = open_room(client)
        with client.websocket_connect(url(b)) as wb:
            with client.websocket_connect(url(a)) as wa:
                join_both(client, wa, wb, a, b)
                wa.send_json({"v": 1, "type": "bye"})
            left = collect_until(wb, "peer_left")[-1]  # would hang for 60 s without the fix
            assert isinstance(left, dict) and left["name"] == "Ramesh"
