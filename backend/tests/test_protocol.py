import pytest
from pydantic import ValidationError

from app.models import protocol as pr


def test_parse_hello_defaults() -> None:
    msg = pr.parse_client_message(
        '{"v":1,"type":"hello","name":"Ramesh","language":"kn-IN","consent":true}'
    )
    assert isinstance(msg, pr.Hello)
    assert msg.mode == "auto"
    assert msg.store_transcript is False


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"type":"nope"}',
        '{"type":"hello","name":"x"}',
        '{"type":"mode","mode":"shout"}',
    ],
)
def test_bad_messages_rejected(text: str) -> None:
    with pytest.raises(ValidationError):
        pr.parse_client_message(text)


def test_simple_messages() -> None:
    assert isinstance(pr.parse_client_message('{"type":"ptt_start"}'), pr.PttStart)
    assert isinstance(pr.parse_client_message('{"type":"ping"}'), pr.Ping)
    assert isinstance(pr.parse_client_message('{"type":"mode","mode":"ptt"}'), pr.SetMode)


def test_server_messages_carry_version_and_type() -> None:
    data = pr.Pong().model_dump()
    assert data == {"v": 1, "type": "pong"}
    err = pr.ErrorMsg(code="room_full", message="x").model_dump()
    assert err["fatal"] is False
