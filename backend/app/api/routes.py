from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.security import RateLimiter, create_token
from app.models.protocol import SUPPORTED_LANGUAGES
from app.services.rooms import RoomError, RoomRegistry

router = APIRouter()


class JoinRequest(BaseModel):
    name: str
    language: str
    consent: bool


class JoinResponse(BaseModel):
    room_id: str
    code: str
    token: str


def _check(request: Request, body: JoinRequest) -> None:
    limiter: RateLimiter = request.app.state.limiter
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(ip):
        raise HTTPException(429, {"code": "rate_limited", "message": "Too many requests"})
    if not body.consent:
        raise HTTPException(400, {"code": "consent_required", "message": "Consent is required"})
    if body.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(400, {"code": "bad_language", "message": "Unsupported language"})
    if not body.name.strip() or len(body.name) > 40:
        raise HTTPException(400, {"code": "bad_name", "message": "Name must be 1-40 characters"})


@router.post("/rooms", response_model=JoinResponse)
async def create_room(body: JoinRequest, request: Request) -> JoinResponse:
    _check(request, body)
    registry: RoomRegistry = request.app.state.registry
    room = registry.create_room()
    p = registry.add_participant(room, body.name.strip(), body.language, body.consent)
    token = create_token(request.app.state.settings, room.id, p.id, p.name, p.language)
    return JoinResponse(room_id=room.id, code=room.code, token=token)


@router.post("/rooms/{code}/join", response_model=JoinResponse)
async def join_room(code: str, body: JoinRequest, request: Request) -> JoinResponse:
    _check(request, body)
    registry: RoomRegistry = request.app.state.registry
    room = registry.by_code(code)
    if room is None:
        raise HTTPException(404, {"code": "room_not_found", "message": "Room not found"})
    try:
        p = registry.add_participant(room, body.name.strip(), body.language, body.consent)
    except RoomError as exc:
        raise HTTPException(409, {"code": exc.code, "message": str(exc)}) from exc
    token = create_token(request.app.state.settings, room.id, p.id, p.name, p.language)
    return JoinResponse(room_id=room.id, code=room.code, token=token)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics")
async def metrics(request: Request) -> dict[str, object]:
    snap = request.app.state.metrics.snapshot()
    snap["active_rooms"] = len(request.app.state.registry)
    return dict(snap)
