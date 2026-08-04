from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: Literal["ok", "ready"]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    # Infrastructure probes will be added with their adapters in the persistence delivery.
    return HealthResponse(status="ready")
