from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from webhookhub.bootstrap.config import Settings, get_settings
from webhookhub.shared.presentation.health import router as health_router
from webhookhub.shared.presentation.middleware import RequestContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title="WebhookHub API",
        version="0.1.0",
        debug=resolved_settings.debug,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url=None,
    )
    app.state.settings = resolved_settings
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in resolved_settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    )
    app.include_router(health_router)
    return app


app = create_app()
