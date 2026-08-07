import logging

import pytest
from httpx import ASGITransport, AsyncClient

from webhookhub.bootstrap.config import Settings
from webhookhub.main import create_app


@pytest.mark.asyncio
async def test_admin_frontend_is_served(client: AsyncClient) -> None:
    response = await client.get("/admin/")

    assert response.status_code == 200
    assert "Painel operacional" in response.text


@pytest.mark.asyncio
async def test_metrics_reports_requests(client: AsyncClient) -> None:
    await client.get("/health")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "webhookhub_http_requests_total" in response.text
    assert 'path="/health",status="200"' in response.text


@pytest.mark.asyncio
async def test_metrics_can_require_bearer_token() -> None:
    settings = Settings(
        environment="test",
        cors_origins=[],
        metrics_token="secret-metrics",  # noqa: S106
    )
    transport = ASGITransport(app=create_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/metrics")
        allowed = await client.get("/metrics", headers={"Authorization": "Bearer secret-metrics"})

    assert denied.status_code == 401
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_access_log_contains_request_context(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="webhookhub.http"):
        await client.get(
            "/health", headers={"X-Request-ID": "9e8ee3cc-e281-4d92-9c62-29f4b36beea5"}
        )

    assert '"event":"http_request"' in caplog.text
    assert '"request_id":"9e8ee3cc-e281-4d92-9c62-29f4b36beea5"' in caplog.text
