import time
from collections import defaultdict, deque
from typing import Any

import jwt

from app.core.config import Settings


class TokenError(Exception):
    pass


def create_token(
    settings: Settings, room_id: str, participant_id: str, name: str, lang: str
) -> str:
    now = int(time.time())
    claims = {
        "rid": room_id,
        "pid": participant_id,
        "name": name,
        "lang": lang,
        "iat": now,
        "exp": now + settings.jwt_ttl_s,
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def decode_token(settings: Settings, token: str) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"]
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    return claims


class RateLimiter:
    """Sliding-window limiter keyed by client IP (in-memory, single process)."""

    def __init__(self, max_calls: int, window_s: float = 60.0) -> None:
        self._max = max_calls
        self._window = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self._window:
            hits.popleft()
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True
