import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from webhookhub.applications.application.security import (
    UnsafeEndpointError,
    sign_webhook,
    validate_endpoint_url,
)
from webhookhub.applications.domain.models import DeliveryStatus, WebhookDelivery


class HttpSender(Protocol):
    async def post(
        self, url: str, *, content: bytes, headers: dict[str, str]
    ) -> httpx.Response: ...


@dataclass(frozen=True)
class DeliveryResult:
    dead: bool
    succeeded: bool


async def deliver(
    delivery: WebhookDelivery,
    *,
    url: str,
    payload: dict[str, object],
    signing_secret: str,
    sender: HttpSender,
    max_attempts: int,
    retry_base_seconds: int,
) -> DeliveryResult:
    now = datetime.now(UTC)
    delivery.attempt_count += 1
    delivery.last_error = None
    try:
        safe_url = await validate_endpoint_url(url)
        timestamp = int(now.timestamp())
        body = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        response = await sender.post(
            safe_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "WebhookHub/0.1",
                "X-Webhook-Event-ID": str(delivery.event_id),
                "X-Webhook-Delivery-ID": str(delivery.id),
                "X-Webhook-Timestamp": str(timestamp),
                "X-Webhook-Signature": f"v1={sign_webhook(signing_secret, timestamp, body)}",
            },
        )
        delivery.last_status_code = response.status_code
        if 200 <= response.status_code < 300:
            delivery.status = DeliveryStatus.SUCCEEDED
            delivery.delivered_at = now
            return DeliveryResult(dead=False, succeeded=True)
        delivery.last_error = f"HTTP {response.status_code}"
    except (httpx.HTTPError, UnsafeEndpointError) as error:
        delivery.last_error = str(error)[:2000]

    if delivery.attempt_count >= max_attempts:
        delivery.status = DeliveryStatus.DEAD
        return DeliveryResult(dead=True, succeeded=False)
    delay = retry_base_seconds * (2 ** (delivery.attempt_count - 1))
    delivery.next_attempt_at = now + timedelta(seconds=delay)
    return DeliveryResult(dead=False, succeeded=False)
