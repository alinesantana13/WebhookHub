import json
from collections.abc import AsyncIterator
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]
from aiokafka.errors import KafkaError  # type: ignore[import-untyped]


class MessagingUnavailableError(RuntimeError):
    """Raised when Kafka cannot serve a readiness probe."""


class KafkaMessaging:
    def __init__(self, bootstrap_servers: list[str]) -> None:
        self.bootstrap_servers = bootstrap_servers

    def producer(self) -> AIOKafkaProducer:
        return AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            enable_idempotence=True,
            value_serializer=lambda value: json.dumps(value).encode(),
        )

    def consumer(self, topic: str, group_id: str) -> AIOKafkaConsumer:
        return AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=json.loads,
        )

    async def ping(self) -> None:
        producer = self.producer()
        try:
            await producer.start()
            await producer.client.force_metadata_update()
        except (KafkaError, OSError) as error:
            raise MessagingUnavailableError from error
        finally:
            await producer.stop()


async def messages(consumer: AIOKafkaConsumer) -> AsyncIterator[dict[str, Any]]:
    async for message in consumer:
        value = message.value
        if isinstance(value, dict):
            yield value
