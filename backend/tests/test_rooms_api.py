from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakePipeline, make_settings

OD = {"name": "Ramesh", "language": "kn-IN", "consent": True}
HI = {"name": "Sita", "language": "hi-IN", "consent": True}


def test_create_and_join(client: TestClient) -> None:
    a = client.post("/rooms", json=OD)
    assert a.status_code == 200
    body = a.json()
    assert len(body["code"]) == 6 and body["token"] and body["room_id"]
    b = client.post(f"/rooms/{body['code']}/join", json=HI)
    assert b.status_code == 200
    assert b.json()["room_id"] == body["room_id"]


def test_room_limit_is_two(client: TestClient) -> None:
    code = client.post("/rooms", json=OD).json()["code"]
    assert client.post(f"/rooms/{code}/join", json=HI).status_code == 200
    third = client.post(f"/rooms/{code}/join", json=HI)
    assert third.status_code == 409
    assert third.json()["detail"]["code"] == "room_full"


def test_join_unknown_code(client: TestClient) -> None:
    resp = client.post("/rooms/000000/join", json=HI)
    assert resp.status_code == 404


def test_consent_required(client: TestClient) -> None:
    resp = client.post("/rooms", json={**OD, "consent": False})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "consent_required"


def test_unsupported_language(client: TestClient) -> None:
    assert client.post("/rooms", json={**OD, "language": "xx-IN"}).status_code == 400


def test_bad_name(client: TestClient) -> None:
    assert client.post("/rooms", json={**OD, "name": "  "}).status_code == 400


def test_rate_limit_per_ip() -> None:
    app = create_app(make_settings(rooms_per_minute=3), FakePipeline())
    with TestClient(app) as tc:
        codes = [tc.post("/rooms", json=OD).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_health_and_metrics(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    m = client.get("/metrics").json()
    assert m["utterances"] == 0 and m["active_rooms"] == 0 and m["latency"] == {}
