from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from webhookhub.applications.application.ingestion import canonical_payload, payload_digest
from webhookhub.applications.domain.models import ApiKey, OutboxMessage, WebhookEvent
from webhookhub.applications.presentation import ingestion


class FakeSession:
    def __init__(self, existing: WebhookEvent | None = None) -> None:
        self.existing = existing
        self.added: list[Any] = []
        self.commit_count = 0

    async def execute(self, _: object, __: object) -> None:
        return None

    async def scalar(self, _: object) -> WebhookEvent | None:
        return self.existing

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        event = cast(WebhookEvent, self.added[0])
        event.id = uuid4()
        event.received_at = datetime.now(UTC)

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, _: object) -> None:
        return None


def test_payload_digest_is_stable_across_key_order() -> None:
    first = {"event": "paid", "data": {"amount": 100, "currency": "BRL"}}
    second = {"data": {"currency": "BRL", "amount": 100}, "event": "paid"}

    assert canonical_payload(first) == canonical_payload(second)
    assert payload_digest(first) == payload_digest(second)


def test_payload_digest_changes_with_content() -> None:
    assert payload_digest({"amount": 100}) != payload_digest({"amount": 101})


@pytest.mark.asyncio
async def test_ingestion_persists_event_and_outbox_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application_id = uuid4()
    key = ApiKey(application_id=application_id, name="Production", key_prefix="whk_test")
    fake = FakeSession()

    async def authenticated(*_: object) -> ApiKey:
        return key

    monkeypatch.setattr(ingestion, "authenticate_api_key", authenticated)
    response = await ingestion.ingest_webhook(
        application_id,
        {"type": "payment.confirmed"},
        cast(AsyncSession, fake),
        "payment-123",
        "whk_secret",
    )

    event = cast(WebhookEvent, fake.added[0])
    message = cast(OutboxMessage, fake.added[1])
    assert response.id == event.id
    assert not response.duplicate
    assert message.event_id == event.id
    assert message.payload["event_id"] == str(event.id)
    assert key.last_used_at is not None
    assert fake.commit_count == 1


@pytest.mark.asyncio
async def test_duplicate_returns_original_event(monkeypatch: pytest.MonkeyPatch) -> None:
    application_id = uuid4()
    payload = {"type": "payment.confirmed"}
    existing = WebhookEvent(
        id=uuid4(),
        application_id=application_id,
        idempotency_key="payment-123",
        payload_hash=payload_digest(payload),
        payload=payload,
        headers={},
        received_at=datetime.now(UTC),
    )
    fake = FakeSession(existing)

    async def authenticated(*_: object) -> ApiKey:
        return ApiKey(application_id=application_id, name="Production")

    monkeypatch.setattr(ingestion, "authenticate_api_key", authenticated)
    response = await ingestion.ingest_webhook(
        application_id, payload, cast(AsyncSession, fake), "payment-123", "whk_secret"
    )

    assert response.id == existing.id
    assert response.duplicate
    assert not fake.added


@pytest.mark.asyncio
async def test_idempotency_key_cannot_be_reused_for_new_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application_id = uuid4()
    existing = WebhookEvent(
        application_id=application_id,
        idempotency_key="payment-123",
        payload_hash=payload_digest({"amount": 100}),
        payload={"amount": 100},
        headers={},
    )
    fake = FakeSession(existing)

    async def authenticated(*_: object) -> ApiKey:
        return ApiKey(application_id=application_id, name="Production")

    monkeypatch.setattr(ingestion, "authenticate_api_key", authenticated)
    with pytest.raises(HTTPException) as raised:
        await ingestion.ingest_webhook(
            application_id,
            {"amount": 101},
            cast(AsyncSession, fake),
            "payment-123",
            "whk_secret",
        )

    assert raised.value.status_code == 409
