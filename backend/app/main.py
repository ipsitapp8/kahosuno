from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import routes, ws
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.core.security import RateLimiter
from app.services.metrics import Metrics
from app.services.pipeline import TranslationPipeline
from app.services.rooms import RoomRegistry
from app.services.sarvam import SarvamClient
from app.services.vad import Segmenter


def create_app(
    settings: Settings | None = None, pipeline: ws.PipelineLike | None = None
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client: SarvamClient | None = None
        if pipeline is None:
            client = SarvamClient(settings)
            app.state.pipeline = TranslationPipeline(client)
        try:
            yield
        finally:
            if client:
                await client.aclose()

    app = FastAPI(title="Bharat Call Assistant", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.pipeline = pipeline
    app.state.metrics = Metrics()
    app.state.limiter = RateLimiter(settings.rooms_per_minute)
    app.state.registry = RoomRegistry(
        segmenter_factory=lambda: Segmenter(max_ms=settings.max_utterance_s * 1000),
        grace_s=settings.reconnect_grace_s,
        join_ttl_s=settings.jwt_ttl_s,
        on_left=ws.notify_left,
    )
    app.include_router(routes.router)
    app.include_router(ws.router)
    return app


setup_logging()
app = create_app()
