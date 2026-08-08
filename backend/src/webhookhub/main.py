import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from webhookhub.applications.presentation.ingestion import router as ingestion_router
from webhookhub.applications.presentation.routes import router as applications_router
from webhookhub.bootstrap.config import Settings, get_settings
from webhookhub.identity.presentation.routes import organizations_router
from webhookhub.identity.presentation.routes import router as identity_router
from webhookhub.shared.infrastructure.cache import RedisCache
from webhookhub.shared.infrastructure.database import Database
from webhookhub.shared.infrastructure.messaging import KafkaMessaging
from webhookhub.shared.presentation.health import router as health_router
from webhookhub.shared.presentation.middleware import (
    HttpMetrics,
    HttpObservabilityMiddleware,
    RequestContextMiddleware,
)
from webhookhub.shared.presentation.observability import router as observability_router


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    logging.basicConfig(
        level=resolved_settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    resolved_database = database or Database(
        resolved_settings.postgres_dsn,
        echo=resolved_settings.debug,
    )
    cache = RedisCache(resolved_settings.redis_dsn)
    messaging = KafkaMessaging(resolved_settings.kafka_bootstrap_servers)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        await cache.close()
        await resolved_database.dispose()

    app = FastAPI(
        title="WebhookHub API",
        version="0.1.0",
        debug=resolved_settings.debug,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = resolved_database
    app.state.cache = cache
    app.state.messaging = messaging
    app.state.http_metrics = HttpMetrics()
    app.dependency_overrides[get_settings] = lambda: resolved_settings
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(HttpObservabilityMiddleware, metrics=app.state.http_metrics)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in resolved_settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-API-Key",
            "X-Request-ID",
        ],
    )
    app.include_router(health_router)
    app.include_router(identity_router)
    app.include_router(organizations_router)
    app.include_router(applications_router)
    app.include_router(ingestion_router)
    app.include_router(observability_router)
    return app


app = create_app()
