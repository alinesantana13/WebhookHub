import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

import httpx
from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webhookhub.applications.application.delivery import deliver
from webhookhub.applications.domain.models import (
    DeliveryStatus,
    Endpoint,
    OutboxMessage,
    WebhookDelivery,
    WebhookEvent,
)
from webhookhub.bootstrap.config import Settings, get_settings
from webhookhub.shared.infrastructure.database import Database
from webhookhub.shared.infrastructure.messaging import KafkaMessaging, messages

logger = logging.getLogger(__name__)


async def publish_outbox_batch(
    session: AsyncSession, producer: AIOKafkaProducer, *, limit: int = 100
) -> int:
    rows = list(
        (
            await session.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.published_at.is_(None))
                .order_by(OutboxMessage.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for row in rows:
        await producer.send_and_wait(row.topic, row.payload, key=str(row.event_id).encode())
        row.published_at = datetime.now(UTC)
    await session.commit()
    return len(rows)


async def ensure_deliveries(session: AsyncSession, event_id: UUID, application_id: UUID) -> None:
    endpoints = (
        await session.scalars(
            select(Endpoint).where(
                Endpoint.application_id == application_id, Endpoint.enabled.is_(True)
            )
        )
    ).all()
    existing = set(
        (
            await session.scalars(
                select(WebhookDelivery.endpoint_id).where(WebhookDelivery.event_id == event_id)
            )
        ).all()
    )
    for endpoint in endpoints:
        if endpoint.id not in existing:
            session.add(WebhookDelivery(event_id=event_id, endpoint_id=endpoint.id))
    await session.commit()


async def process_delivery(
    session: AsyncSession,
    delivery_row: WebhookDelivery,
    sender: httpx.AsyncClient,
    producer: AIOKafkaProducer,
    settings: Settings,
) -> None:
    endpoint = await session.get(Endpoint, delivery_row.endpoint_id)
    event = await session.get(WebhookEvent, delivery_row.event_id)
    if endpoint is None or event is None or not endpoint.enabled:
        delivery_row.status = DeliveryStatus.DEAD
        delivery_row.last_error = "Endpoint or event is no longer available"
        await session.commit()
        return
    result = await deliver(
        delivery_row,
        url=endpoint.url,
        payload=event.payload,
        sender=sender,
        max_attempts=settings.delivery_max_attempts,
        retry_base_seconds=settings.delivery_retry_base_seconds,
    )
    if result.dead:
        await producer.send_and_wait(
            settings.kafka_dlq_topic,
            {
                "delivery_id": str(delivery_row.id),
                "event_id": str(delivery_row.event_id),
                "endpoint_id": str(delivery_row.endpoint_id),
                "attempts": delivery_row.attempt_count,
                "error": delivery_row.last_error,
            },
            key=str(delivery_row.event_id).encode(),
        )
    await session.commit()


async def claim_due_delivery(session: AsyncSession) -> WebhookDelivery | None:
    return await session.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.status == DeliveryStatus.PENDING,
            WebhookDelivery.next_attempt_at <= datetime.now(UTC),
        )
        .order_by(WebhookDelivery.next_attempt_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


async def run_worker(settings: Settings | None = None) -> None:  # pragma: no cover
    config = settings or get_settings()
    database = Database(config.postgres_dsn)
    messaging = KafkaMessaging(config.kafka_bootstrap_servers)
    producer = messaging.producer()
    consumer = messaging.consumer(config.kafka_events_topic, config.kafka_consumer_group)
    await producer.start()
    await consumer.start()

    async def outbox_loop() -> None:
        while True:
            async with database.session() as session:
                count = await publish_outbox_batch(session, producer)
            if count == 0:
                await asyncio.sleep(config.worker_poll_seconds)

    async def consume_loop() -> None:
        async for value in messages(consumer):
            try:
                event_id = UUID(str(value["event_id"]))
                application_id = UUID(str(value["application_id"]))
            except (KeyError, ValueError, TypeError):
                logger.exception("Discarding malformed webhook event")
            else:
                async with database.session() as session:
                    await ensure_deliveries(session, event_id, application_id)
            await consumer.commit()

    async def delivery_loop() -> None:
        async with httpx.AsyncClient(
            timeout=config.delivery_timeout_seconds,
            follow_redirects=False,
        ) as sender:
            while True:
                async with database.session() as session:
                    row = await claim_due_delivery(session)
                    if row is not None:
                        await process_delivery(session, row, sender, producer, config)
                if row is None:
                    await asyncio.sleep(config.worker_poll_seconds)

    tasks = [
        asyncio.create_task(outbox_loop()),
        asyncio.create_task(consume_loop()),
        asyncio.create_task(delivery_loop()),
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        await consumer.stop()
        await producer.stop()
        await database.dispose()


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=get_settings().log_level)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
