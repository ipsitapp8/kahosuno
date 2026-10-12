from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api import routes, ws
from app.core.config import Settings, get_settings
from app.core.logging import install_token_redaction, setup_logging
from app.core.security import RateLimiter
from app.services.factory import Providers, build_providers
from app.services.metrics import Metrics
from app.services.rooms import RoomRegistry
from app.services.scam.engine import ScamShield, ShieldConfig
from app.services.scam.llm import ChatProvider, LlmClassifier
from app.services.store import CallStore
from app.services.vad import Segmenter


def create_app(
    settings: Settings | None = None,
    pipeline: ws.PipelineLike | None = None,
    chat: ChatProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    settings.check_production()  # refuses to start with a weak signing secret in production
    store = CallStore(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        providers: Providers | None = None
        if pipeline is None:
            providers = build_providers(settings)
            app.state.pipeline = providers.pipeline()
            app.state.chat = providers.chat
        install_token_redaction()  # uvicorn has finished configuring its loggers by now
        await store.init()
        await store.prune_transcripts(settings.transcript_retention_days)
        try:
            yield
        finally:
            if providers:
                await providers.aclose()
            await store.close()

    app = FastAPI(title="Bharat Call Assistant", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.pipeline = pipeline
    app.state.chat = chat
    app.state.store = store
    app.state.metrics = Metrics()
    app.state.limiter = RateLimiter(settings.rooms_per_minute)
    app.state.ws_limiter = RateLimiter(settings.ws_connects_per_minute)

    @app.middleware("http")
    async def safe_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def make_shield() -> ScamShield | None:
        if not settings.scam_enabled:
            return None
        llm = None
        if settings.scam_llm_enabled and app.state.chat is not None:
            llm = LlmClassifier(app.state.chat, settings.scam_llm_timeout_s)
        cfg = ShieldConfig(
            llm_min_interval_s=settings.scam_llm_min_interval_s,
            llm_max_calls=settings.scam_llm_max_calls,
        )
        return ScamShield(cfg, llm)

    app.state.registry = RoomRegistry(
        segmenter_factory=lambda: Segmenter(max_ms=settings.max_utterance_s * 1000),
        grace_s=settings.reconnect_grace_s,
        join_ttl_s=settings.join_ttl_s,
        on_left=ws.notify_left,
        shield_factory=make_shield,
        on_closed=store.save_room_safely,
    )
    app.include_router(routes.router)
    app.include_router(ws.router)
    return app


setup_logging()
app = create_app()
