from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from webhookhub import worker
from webhookhub.applications.domain.models import (
    DeliveryStatus,
    Endpoint,
    OutboxMessage,
    WebhookDelivery,
    WebhookEvent,
)
from webhookhub.bootstrap.config import Settings


class ScalarRows:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def all(self) -> list[Any]:
        return self.values


class Session:
    def __init__(self, scalar_batches: list[list[Any]] | None = None) -> None:
        self.scalar_batches = scalar_batches or []
        self.added: list[Any] = []
        self.commits = 0
        self.objects: dict[tuple[type[Any], Any], Any] = {}

    async def scalars(self, _: object) -> ScalarRows:
        return ScalarRows(self.scalar_batches.pop(0))

    async def scalar(self, _: object) -> Any:
        return self.scalar_batches.pop(0)[0] if self.scalar_batches else None

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1

    async def get(self, model: type[Any], identifier: Any) -> Any:
        return self.objects.get((model, identifier))


class Producer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, bytes]] = []

    async def send_and_wait(self, topic: str, value: object, *, key: bytes) -> None:
        self.sent.append((topic, value, key))


@pytest.mark.asyncio
async def test_outbox_is_published_before_being_marked() -> None:
    message = OutboxMessage(
        event_id=uuid4(), topic="webhook.received", payload={"event_id": "event"}
    )
    session = Session([[message]])
    producer = Producer()

    count = await worker.publish_outbox_batch(cast(AsyncSession, session), cast(Any, producer))

    assert count == 1
    assert producer.sent[0][0] == "webhook.received"
    assert message.published_at is not None
    assert session.commits == 1


@pytest.mark.asyncio
async def test_consumer_creates_only_missing_endpoint_deliveries() -> None:
    event_id = uuid4()
    application_id = uuid4()
    old = Endpoint(id=uuid4(), application_id=application_id, name="Old", url="https://a.test/")
    new = Endpoint(id=uuid4(), application_id=application_id, name="New", url="https://b.test/")
    session = Session([[old, new], [old.id]])

    await worker.ensure_deliveries(cast(AsyncSession, session), event_id, application_id)

    created = cast(WebhookDelivery, session.added[0])
    assert created.endpoint_id == new.id
    assert created.event_id == event_id
    assert session.commits == 1


@pytest.mark.asyncio
async def test_final_failure_is_published_to_dlq(monkeypatch: pytest.MonkeyPatch) -> None:
    application_id = uuid4()
    endpoint = Endpoint(
        id=uuid4(),
        application_id=application_id,
        name="Destination",
        url="https://example.com/",
        enabled=True,
    )
    event = WebhookEvent(
        id=uuid4(),
        application_id=application_id,
        idempotency_key="key",
        payload_hash="hash",
        payload={"type": "test"},
        headers={},
    )
    delivery = WebhookDelivery(
        id=uuid4(),
        event_id=event.id,
        endpoint_id=endpoint.id,
        status=DeliveryStatus.PENDING,
        attempt_count=0,
        next_attempt_at=datetime.now(UTC),
    )
    session = Session()
    session.objects[(Endpoint, endpoint.id)] = endpoint
    session.objects[(WebhookEvent, event.id)] = event
    producer = Producer()

    async def safe(value: str) -> str:
        return value

    monkeypatch.setattr("webhookhub.applications.application.delivery.validate_endpoint_url", safe)

    class FailingSender:
        async def post(self, *_: object, **__: object) -> Any:
            return type("Response", (), {"status_code": 500})()

    settings = Settings(environment="test", cors_origins=[], delivery_max_attempts=1)
    await worker.process_delivery(
        cast(AsyncSession, session),
        delivery,
        cast(Any, FailingSender()),
        cast(Any, producer),
        settings,
    )

    assert delivery.status == DeliveryStatus.DEAD
    assert producer.sent[0][0] == settings.kafka_dlq_topic
    assert session.commits == 1


@pytest.mark.asyncio
async def test_due_delivery_claim_returns_database_result() -> None:
    delivery = WebhookDelivery(event_id=uuid4(), endpoint_id=uuid4())

    result = await worker.claim_due_delivery(cast(AsyncSession, Session([[delivery]])))

    assert result is delivery
