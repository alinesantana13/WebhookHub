from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from webhookhub.bootstrap.config import Settings
from webhookhub.main import create_app
from webhookhub.shared.infrastructure.database import Database


class HealthyTestDatabase(Database):
    def __init__(self) -> None:
        # This test double deliberately avoids constructing an infrastructure engine.
        self.ping_count = 0

    async def ping(self) -> None:
        self.ping_count += 1

    async def dispose(self) -> None:
        return None


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(environment="test", cors_origins=[])
    transport = ASGITransport(app=create_app(settings, database=HealthyTestDatabase()))
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
