from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from webhookhub.shared.infrastructure.database import Database, DatabaseUnavailableError

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: Literal["ok", "ready"]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


def get_database(request: Request) -> Database:
    return request.app.state.database


@router.get("/ready", response_model=HealthResponse)
async def ready(database: Annotated[Database, Depends(get_database)]) -> HealthResponse:
    try:
        await database.ping()
    except DatabaseUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL is unavailable",
        ) from error
    return HealthResponse(status="ready")
