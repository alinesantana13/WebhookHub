import os

import pytest
from sqlalchemy import text

from webhookhub.shared.infrastructure.database import Database


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgresql_accepts_async_connection() -> None:
    dsn = os.getenv("WEBHOOKHUB_TEST_POSTGRES_DSN")
    if dsn is None:
        pytest.skip("WEBHOOKHUB_TEST_POSTGRES_DSN is not configured")

    database = Database(dsn)
    try:
        await database.ping()
        async with database.session() as session:
            result = await session.scalar(text("SELECT 1"))
    finally:
        await database.dispose()

    assert result == 1
