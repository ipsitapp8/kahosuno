"""Security hardening: startup checks, limits, token lifetime, headers."""

import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import create_token, decode_token
from app.main import create_app
from tests.conftest import FakePipeline, make_settings
from tests.test_call_e2e import recv, url
from tests.test_rooms_api import HI, OD

STRONG = "x" * 40


@pytest.mark.parametrize(
    "secret", ["change-me", "change-me-to-a-long-random-string", "", "short-secret"]
)
def test_production_refuses_weak_secrets(secret: str) -> None:
    settings = Settings(app_env="production", jwt_secret=secret)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.check_production()
    with pytest.raises(RuntimeError):
        create_app(settings, FakePipeline())


def test_production_accepts_a_long_secret_and_development_stays_easy() -> None:
    Settings(app_env="production", jwt_secret=STRONG).check_production()  # type: ignore[arg-type]
    Settings(app_env="development", jwt_secret="change-me").check_production()  # type: ignore[arg-type]


def test_join_token_lasts_long_enough_for_a_real_call() -> None:
    settings = make_settings()
    claims = decode_token(settings, create_token(settings, "r", "p", "n", "kn-IN"))
    assert claims["exp"] - claims["iat"] == 3600  # reconnects work for a full hour


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = create_token(make_settings(jwt_secret="a" * 40), "r", "p", "n", "kn-IN")
    with pytest.raises(Exception):  # noqa: B017  (TokenError)
        decode_token(make_settings(jwt_secret="b" * 40), forged)


def test_unused_seat_is_given_back_but_token_would_still_be_valid_for_reconnects() -> None:
    app = create_app(
        make_settings(join_ttl_s=0.2, database_url="sqlite+aiosqlite:///:memory:"), FakePipeline()
    )
    with TestClient(app) as tc:
        tc.post("/rooms", json=OD)
        assert len(app.state.registry) == 1
        time.sleep(0.8)
        assert len(app.state.registry) == 0


def test_room_cap_protects_server_memory() -> None:
    app = create_app(
        make_settings(max_rooms=2, database_url="sqlite+aiosqlite:///:memory:"), FakePipeline()
    )
    with TestClient(app) as tc:
        assert tc.post("/rooms", json=OD).status_code == 200
        assert tc.post("/rooms", json=HI).status_code == 200
        busy = tc.post("/rooms", json=OD)
        assert busy.status_code == 503
        assert busy.json()["detail"]["code"] == "server_busy"


def test_websocket_connection_attempts_are_rate_limited_per_ip() -> None:
    app = create_app(
        make_settings(ws_connects_per_minute=2, database_url="sqlite+aiosqlite:///:memory:"),
        FakePipeline(),
    )
    with TestClient(app) as tc:
        a = tc.post("/rooms", json=OD).json()
        codes = []
        for attempt in range(3):
            with tc.websocket_connect(url(a)) as ws:
                if attempt < 2:
                    ws.send_json({"v": 1, "type": "ping"})  # a normal connection answers this
                reply = recv(ws)
                assert isinstance(reply, dict)
                codes.append(reply["code"])
        # two normal connections ("send hello first"), then the third is refused
        assert codes == ["bad_message", "bad_message", "rate_limited"]


def test_http_responses_carry_safe_headers(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["cache-control"] == "no-store"


def test_cannot_reuse_someone_elses_token_in_another_room(client: TestClient) -> None:
    a = client.post("/rooms", json=OD).json()
    b = client.post("/rooms", json=HI).json()
    with client.websocket_connect(f"/ws/v1/rooms/{b['room_id']}?token={a['token']}") as ws:
        assert recv(ws)["code"] == "room_not_found"  # type: ignore[call-overload]


# ---- join tokens must never reach a log ----
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJyaWQiOiJ4In0.c2lnbmF0dXJl"


def _format(logger_name: str, msg: str, args: tuple[object, ...]) -> str:
    import io
    import logging

    from app.core.logging import JsonFormatter, install_token_redaction

    # Mirror the real setup: one handler on the root logger, and redaction installed on it.
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    install_token_redaction()
    logger = logging.getLogger(logger_name)
    old_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        logger.info(msg, *args)
    finally:
        logger.setLevel(old_level)
        root.removeHandler(handler)
    return stream.getvalue()


def test_uvicorn_access_log_does_not_show_the_join_token() -> None:
    # This is the exact shape uvicorn uses for a websocket upgrade line.
    out = _format(
        "uvicorn.access",
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.5:4242", "WebSocket", f"/ws/v1/rooms/abc?token={JWT}", "1.1", 101),
    )
    assert JWT not in out and "eyJ" not in out
    assert "token=<redacted>" in out
    assert "/ws/v1/rooms/abc" in out  # the rest of the line is still useful


def test_redaction_also_covers_plain_messages_and_other_params() -> None:
    out = _format("app.something", f"connect failed for ws://h/x?token={JWT}&v=1", ())
    assert JWT not in out
    assert "v=1" in out
