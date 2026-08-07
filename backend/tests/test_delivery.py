from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import httpx
import pytest

from webhookhub.applications.application.delivery import deliver
from webhookhub.applications.domain.models import DeliveryStatus, WebhookDelivery


class Sender:
    def __init__(self, status_code: int | None = 204) -> None:
        self.status_code = status_code
        self.requests: list[tuple[str, object, dict[str, str]]] = []

    async def post(self, url: str, *, json: object, headers: dict[str, str]) -> httpx.Response:
        self.requests.append((url, json, headers))
        if self.status_code is None:
            raise httpx.ConnectError("destination unavailable")
        return httpx.Response(self.status_code)


def row() -> WebhookDelivery:
    return WebhookDelivery(
        id=uuid4(),
        event_id=uuid4(),
        endpoint_id=uuid4(),
        status=DeliveryStatus.PENDING,
        attempt_count=0,
        next_attempt_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_successful_delivery_records_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def safe(value: str) -> str:
        return value

    monkeypatch.setattr("webhookhub.applications.application.delivery.validate_endpoint_url", safe)
    delivery = row()
    sender = Sender()

    result = await deliver(
        delivery,
        url="https://example.com/hook",
        payload={"paid": True},
        sender=sender,
        max_attempts=3,
        retry_base_seconds=5,
    )

    assert result.succeeded and not result.dead
    assert delivery.status == DeliveryStatus.SUCCEEDED
    assert delivery.delivered_at is not None
    assert sender.requests[0][2]["X-Webhook-Event-ID"] == str(delivery.event_id)


@pytest.mark.asyncio
async def test_failed_delivery_is_scheduled_with_exponential_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def safe(value: str) -> str:
        return value

    monkeypatch.setattr("webhookhub.applications.application.delivery.validate_endpoint_url", safe)
    delivery = row()
    before = delivery.next_attempt_at

    result = await deliver(
        delivery,
        url="https://example.com/hook",
        payload={},
        sender=Sender(503),
        max_attempts=3,
        retry_base_seconds=5,
    )

    assert not result.succeeded and not result.dead
    assert delivery.status == DeliveryStatus.PENDING
    assert delivery.last_error == "HTTP 503"
    assert delivery.next_attempt_at > before


@pytest.mark.asyncio
async def test_last_network_failure_moves_delivery_to_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def safe(value: str) -> str:
        return value

    monkeypatch.setattr("webhookhub.applications.application.delivery.validate_endpoint_url", safe)
    delivery = row()
    delivery.attempt_count = 2

    result = await deliver(
        delivery,
        url="https://example.com/hook",
        payload={},
        sender=cast(Sender, Sender(None)),
        max_attempts=3,
        retry_base_seconds=5,
    )

    assert result.dead and not result.succeeded
    assert delivery.status == DeliveryStatus.DEAD
    assert delivery.last_error == "destination unavailable"
