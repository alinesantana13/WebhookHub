from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from webhookhub.applications.application.security import hash_api_key
from webhookhub.applications.domain.models import (
    ApiKey,
    Application,
    DeliveryStatus,
    Endpoint,
    WebhookDelivery,
)
from webhookhub.applications.presentation import routes
from webhookhub.applications.presentation.routes import EndpointRequest, NamedRequest
from webhookhub.identity.domain.models import Membership, OrganizationRole, User


class FakeSession:
    def __init__(
        self,
        *,
        application: Application | None = None,
        membership: Membership | None = None,
    ) -> None:
        self.application = application
        self.membership = membership
        self.added: list[Any] = []
        self.commit_count = 0

    async def get(self, model: type[Any], _: object) -> Any:
        assert model is Application
        return self.application

    async def scalar(self, _: object) -> Any:
        return self.membership

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, value: object) -> None:
        if isinstance(value, (ApiKey, Endpoint)):
            value.id = uuid4()
            value.created_at = datetime.now(UTC)


def user() -> User:
    return User(id=uuid4(), email="owner@example.com", password_hash="hash", name="Owner")  # noqa: S106


def application() -> Application:
    return Application(id=uuid4(), organization_id=uuid4(), name="Payments")


def membership(app: Application, current_user: User, role: OrganizationRole) -> Membership:
    return Membership(organization_id=app.organization_id, user_id=current_user.id, role=role)


@pytest.mark.asyncio
async def test_membership_is_required() -> None:
    with pytest.raises(HTTPException) as raised:
        await routes.require_membership(uuid4(), uuid4(), cast(AsyncSession, FakeSession()))

    assert raised.value.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_write() -> None:
    app = application()
    current_user = user()
    fake = FakeSession(membership=membership(app, current_user, OrganizationRole.MEMBER))

    with pytest.raises(HTTPException) as raised:
        await routes.require_membership(
            app.organization_id, current_user.id, cast(AsyncSession, fake), write=True
        )

    assert raised.value.detail == "Administrator role required"


@pytest.mark.asyncio
async def test_missing_application_returns_not_found() -> None:
    with pytest.raises(HTTPException) as raised:
        await routes.get_application(uuid4(), cast(AsyncSession, FakeSession()))

    assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_api_key_is_returned_once_and_persisted_as_hash() -> None:
    app = application()
    current_user = user()
    fake = FakeSession(
        application=app,
        membership=membership(app, current_user, OrganizationRole.ADMIN),
    )

    response = await routes.create_api_key(
        app.id, NamedRequest(name="Production"), current_user, cast(AsyncSession, fake)
    )

    stored = cast(ApiKey, fake.added[0])
    assert response.key.startswith("whk_")
    assert stored.key_hash == hash_api_key(response.key)
    assert stored.key_hash != response.key
    assert fake.commit_count == 1


@pytest.mark.asyncio
async def test_endpoint_is_validated_before_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    app = application()
    current_user = user()
    fake = FakeSession(
        application=app,
        membership=membership(app, current_user, OrganizationRole.OWNER),
    )

    async def safe_url(_: str) -> str:
        return "https://example.com/hook"

    monkeypatch.setattr(routes, "validate_endpoint_url", safe_url)
    result = await routes.create_endpoint(
        app.id,
        EndpointRequest(name="Primary", url="https://EXAMPLE.com/hook"),
        current_user,
        cast(AsyncSession, fake),
    )

    stored = cast(Endpoint, fake.added[0])
    assert result.id == stored.id
    assert stored.url == "https://example.com/hook"
    assert result.signing_secret.startswith("whsec_")


@pytest.mark.asyncio
async def test_delivery_can_be_replayed() -> None:
    app = application()
    current_user = user()
    member = membership(app, current_user, OrganizationRole.ADMIN)
    delivery = WebhookDelivery(
        id=uuid4(),
        event_id=uuid4(),
        endpoint_id=uuid4(),
        status=DeliveryStatus.DEAD,
        attempt_count=5,
        last_status_code=503,
        last_error="HTTP 503",
        delivered_at=datetime.now(UTC),
    )

    class ReplaySession(FakeSession):
        def __init__(self) -> None:
            super().__init__(application=app)
            self.results = [member, delivery]

        async def scalar(self, _: object) -> Any:
            return self.results.pop(0)

        async def refresh(self, _: object) -> None:
            return None

    fake = ReplaySession()
    result = await routes.replay_delivery(
        app.id, delivery.id, current_user, cast(AsyncSession, fake)
    )

    assert result.status == DeliveryStatus.PENDING
    assert result.attempt_count == 0
    assert result.last_error is None
    assert result.delivered_at is None
    assert fake.commit_count == 1
