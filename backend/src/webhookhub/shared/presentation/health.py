from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from webhookhub.bootstrap.config import Settings
from webhookhub.shared.infrastructure.cache import CacheUnavailableError, RedisCache
from webhookhub.shared.infrastructure.database import Database, DatabaseUnavailableError
from webhookhub.shared.infrastructure.messaging import KafkaMessaging, MessagingUnavailableError

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: Literal["ok", "ready"]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_dependencies(request: Request) -> tuple[Settings, RedisCache, KafkaMessaging]:
    return request.app.state.settings, request.app.state.cache, request.app.state.messaging


@router.get("/ready", response_model=HealthResponse)
async def ready(
    database: Annotated[Database, Depends(get_database)],
    dependencies: Annotated[tuple[Settings, RedisCache, KafkaMessaging], Depends(get_dependencies)],
) -> HealthResponse:
    try:
        await database.ping()
    except DatabaseUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL is unavailable",
        ) from error
    settings, cache, messaging = dependencies
    # Unit/ASGI tests intentionally have no external infrastructure.
    if settings.environment != "test":
        try:
            await cache.ping()
        except CacheUnavailableError as error:
            raise HTTPException(status_code=503, detail="Redis is unavailable") from error
        try:
            await messaging.ping()
        except MessagingUnavailableError as error:
            raise HTTPException(status_code=503, detail="Kafka is unavailable") from error
    return HealthResponse(status="ready")
