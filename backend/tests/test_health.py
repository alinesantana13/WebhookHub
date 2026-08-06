import pytest
from httpx import ASGITransport, AsyncClient

from webhookhub.bootstrap.config import Settings
from webhookhub.main import create_app
from webhookhub.shared.infrastructure.database import DatabaseUnavailableError


class UnavailableTestDatabase:
    async def ping(self) -> None:
        raise DatabaseUnavailableError

    async def dispose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


@pytest.mark.asyncio
async def test_ready_returns_ready(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_valid_request_id_is_preserved(client: AsyncClient) -> None:
    request_id = "9e8ee3cc-e281-4d92-9c62-29f4b36beea5"

    response = await client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["x-request-id"] == request_id


@pytest.mark.asyncio
async def test_invalid_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "unsafe-value"})

    assert response.headers["x-request-id"] != "unsafe-value"


@pytest.mark.asyncio
async def test_ready_returns_service_unavailable_when_database_is_down() -> None:
    settings = Settings(environment="test", cors_origins=[])
    app = create_app(settings)
    app.state.database = UnavailableTestDatabase()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "PostgreSQL is unavailable"}
