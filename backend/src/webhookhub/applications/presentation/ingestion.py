from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from webhookhub.applications.application.ingestion import payload_digest
from webhookhub.applications.application.security import hash_api_key
from webhookhub.applications.domain.models import ApiKey, OutboxMessage, WebhookEvent
from webhookhub.identity.presentation.routes import get_session

router = APIRouter(tags=["ingestion"])


class IngestionResponse(BaseModel):
    id: UUID
    application_id: UUID
    received_at: datetime
    duplicate: bool


async def authenticate_api_key(application_id: UUID, raw_key: str, session: AsyncSession) -> ApiKey:
    key = await session.scalar(
        select(ApiKey).where(
            ApiKey.application_id == application_id,
            ApiKey.key_hash == hash_api_key(raw_key),
            ApiKey.revoked_at.is_(None),
        )
    )
    if key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key


@router.post(
    "/applications/{application_id}/webhooks",
    response_model=IngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_webhook(
    application_id: UUID,
    payload: dict[str, Any],
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    api_key: Annotated[str, Header(alias="X-API-Key", min_length=1, max_length=256)],
) -> IngestionResponse:
    key = await authenticate_api_key(application_id, api_key, session)
    digest = payload_digest(payload)

    # The PostgreSQL advisory lock serializes concurrent requests for the same
    # application/key pair, making the read-then-insert idempotency check deterministic.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{application_id}:{idempotency_key}"},
    )
    existing = await session.scalar(
        select(WebhookEvent).where(
            WebhookEvent.application_id == application_id,
            WebhookEvent.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.payload_hash != digest:
            raise HTTPException(status_code=409, detail="Idempotency key reused with new payload")
        await session.commit()
        return IngestionResponse(
            id=existing.id,
            application_id=existing.application_id,
            received_at=existing.received_at,
            duplicate=True,
        )

    event = WebhookEvent(
        application_id=application_id,
        idempotency_key=idempotency_key,
        payload_hash=digest,
        payload=payload,
        headers={},
    )
    session.add(event)
    await session.flush()
    session.add(
        OutboxMessage(
            event_id=event.id,
            topic="webhook.received",
            payload={"event_id": str(event.id), "application_id": str(application_id)},
        )
    )
    key.last_used_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(event)
    return IngestionResponse(
        id=event.id,
        application_id=event.application_id,
        received_at=event.received_at,
        duplicate=False,
    )
