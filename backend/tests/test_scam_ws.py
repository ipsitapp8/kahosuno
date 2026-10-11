"""The scam shield inside a live call: alerts go to the listener only."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakePipeline, make_settings
from tests.helpers import speech_pcm
from tests.test_call_e2e import (
    collect_until,
    join_both,
    open_room,
    recv,
    speak,
    sync,
    types,
    url,
)
from tests.test_scam_engine import FakeChat, verdict

SCAM = "मैं बैंक से बोल रहा हूँ, आपका केवाईसी अपडेट नहीं हुआ, तुरंत अपना ओटीपी बताइए।"


def test_scam_alert_goes_to_listener_only(client: TestClient, pipeline: FakePipeline) -> None:
    pipeline.transcript = SCAM
    a, b = open_room(client)
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        join_both(client, wa, wb, a, b)
        speak(wa, speech_pcm())  # A is the (pretend) scammer, B is the listener

        heard = collect_until(wb, "scam_alert")
        alert = heard[-1]
        assert isinstance(alert, dict)
        assert alert["level"] == "high" and alert["category"] == "credential_request"
        assert 1 <= len(alert["reasons_hinglish"]) <= 3

        # The speaker sees their transcript and latency, but never the warning.
        said = collect_until(wa, "latency")
        assert "scam_alert" not in types(said)
        assert "scam_alert" not in types(sync(wa))


def test_normal_call_gets_no_alert(client: TestClient, pipeline: FakePipeline) -> None:
    pipeline.transcript = "ಅಮ್ಮ, ನಾನು ಸುರಕ್ಷಿತವಾಗಿ ತಲುಪಿದ್ದೇನೆ."
    a, b = open_room(client)
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        join_both(client, wa, wb, a, b)
        speak(wa, speech_pcm())
        heard = collect_until(wb, "latency")
        assert "scam_alert" not in types(heard) and "scam_alert" not in types(sync(wb))


def test_the_other_direction_is_watched_too(client: TestClient, pipeline: FakePipeline) -> None:
    pipeline.transcript = SCAM
    a, b = open_room(client)
    with client.websocket_connect(url(a)) as wa, client.websocket_connect(url(b)) as wb:
        join_both(client, wa, wb, a, b)
        speak(wb, speech_pcm())  # now B talks, so A must be the one warned
        assert collect_until(wa, "scam_alert")[-1]["level"] == "high"  # type: ignore[call-overload]


def test_shield_can_be_switched_off() -> None:
    app = create_app(make_settings(scam_enabled=False), FakePipeline())
    with TestClient(app) as tc:
        a, _ = open_room(tc)
        room = app.state.registry.get(a["room_id"])
        assert all(p.shield is None for p in room.participants.values())


def test_llm_layer_is_optional_by_config() -> None:
    chat = FakeChat([verdict(50)])
    for enabled in (True, False):
        settings = make_settings(scam_llm_enabled=enabled)
        app = create_app(settings, FakePipeline(), chat=chat)
        with TestClient(app) as tc:
            a, _ = open_room(tc)
            room = app.state.registry.get(a["room_id"])
            shields = [p.shield for p in room.participants.values()]
            assert all(s is not None and s.llm_enabled is enabled for s in shields)


def test_demo_survives_llm_outage() -> None:
    """Sarvam credits run out: the LLM errors, rules keep protecting the call."""
    pipeline = FakePipeline()
    pipeline.transcript = SCAM
    chat = FakeChat(error=RuntimeError("402 insufficient credits"))
    app = create_app(make_settings(), pipeline, chat=chat)
    with TestClient(app) as tc:
        a, b = open_room(tc)
        with tc.websocket_connect(url(a)) as wa, tc.websocket_connect(url(b)) as wb:
            join_both(tc, wa, wb, a, b)
            speak(wa, speech_pcm())
            assert collect_until(wb, "scam_alert")[-1]["level"] == "high"  # type: ignore[call-overload]
            assert "latency" in types(collect_until(wa, "latency"))
            assert recv(wb)  # the call is still alive
