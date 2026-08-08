from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from webhookhub.applications.application.security import hash_api_key
from webhookhub.applications.domain.models import (
    ApiKey,
    Application,
    DeliveryStatus,
    Endpoint,
    OperationalAlert,
    WebhookDelivery,
    WebhookEvent,
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
        self.deleted: list[Any] = []
        self.commit_count = 0
        self.rollback_count = 0

    async def get(self, model: type[Any], _: object) -> Any:
        assert model is Application
        return self.application

    async def scalar(self, _: object) -> Any:
        return self.membership

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def delete(self, value: Any) -> None:
        self.deleted.append(value)

    async def refresh(self, value: object) -> None:
        if isinstance(value, (ApiKey, Application, Endpoint)):
            value.id = uuid4()
            value.created_at = datetime.now(UTC)


def user() -> User:
    return User(id=uuid4(), email="owner@example.com", password_hash="hash", name="Owner")  # noqa: S106


def application() -> Application:
    return Application(id=uuid4(), organization_id=uuid4(), name="Payments")


def membership(app: Application, current_user: User, role: OrganizationRole) -> Membership:
    return Membership(organization_id=app.organization_id, user_id=current_user.id, role=role)


def test_names_are_trimmed_and_blank_names_are_rejected() -> None:
    assert NamedRequest(name="  Payments  ").name == "Payments"
    with pytest.raises(ValidationError):
        NamedRequest(name="   ")


@pytest.mark.asyncio
async def test_duplicate_application_name_returns_conflict() -> None:
    app = application()
    current_user = user()

    class DuplicateSession(FakeSession):
        async def commit(self) -> None:
            raise IntegrityError("INSERT", {}, Exception("duplicate"))

    fake = DuplicateSession(
        membership=membership(app, current_user, OrganizationRole.OWNER),
    )
    with pytest.raises(HTTPException) as raised:
        await routes.create_application(
            app.organization_id,
            NamedRequest(name="Payments"),
            current_user,
            cast(AsyncSession, fake),
        )

    assert raised.value.status_code == 409
    assert fake.rollback_count == 1


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
async def test_application_can_be_deleted_by_an_admin() -> None:
    app = application()
    current_user = user()
    fake = FakeSession(
        application=app,
        membership=membership(app, current_user, OrganizationRole.ADMIN),
    )

    await routes.delete_application(app.id, current_user, cast(AsyncSession, fake))

    assert fake.deleted == [app]
    assert fake.commit_count == 1


@pytest.mark.asyncio
async def test_api_key_can_be_revoked_or_deleted() -> None:
    app = application()
    current_user = user()
    member = membership(app, current_user, OrganizationRole.OWNER)
    key = ApiKey(id=uuid4(), application_id=app.id, name="Production")

    class KeySession(FakeSession):
        def __init__(self) -> None:
            super().__init__(application=app)
            self.results: list[Any] = [member, key, member, key]

        async def scalar(self, _: object) -> Any:
            return self.results.pop(0)

    fake = KeySession()
    await routes.revoke_api_key(app.id, key.id, current_user, cast(AsyncSession, fake))
    assert key.revoked_at is not None

    await routes.delete_api_key(app.id, key.id, current_user, cast(AsyncSession, fake))
    assert fake.deleted == [key]
    assert fake.commit_count == 2


@pytest.mark.asyncio
async def test_active_api_key_cannot_be_deleted() -> None:
    app = application()
    current_user = user()
    member = membership(app, current_user, OrganizationRole.OWNER)
    key = ApiKey(id=uuid4(), application_id=app.id, name="Production")

    class KeySession(FakeSession):
        def __init__(self) -> None:
            super().__init__(application=app)
            self.results: list[Any] = [member, key]

        async def scalar(self, _: object) -> Any:
            return self.results.pop(0)

    fake = KeySession()
    with pytest.raises(HTTPException) as raised:
        await routes.delete_api_key(app.id, key.id, current_user, cast(AsyncSession, fake))

    assert raised.value.status_code == 409
    assert not fake.deleted


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
async def test_endpoint_can_be_deleted() -> None:
    app = application()
    current_user = user()
    member = membership(app, current_user, OrganizationRole.ADMIN)
    endpoint = Endpoint(
        id=uuid4(), application_id=app.id, name="Primary", url="https://example.com/hook"
    )

    class EndpointSession(FakeSession):
        def __init__(self) -> None:
            super().__init__(application=app)
            self.results: list[Any] = [member, endpoint]

        async def scalar(self, _: object) -> Any:
            return self.results.pop(0)

    fake = EndpointSession()
    await routes.delete_endpoint(app.id, endpoint.id, current_user, cast(AsyncSession, fake))

    assert fake.deleted == [endpoint]
    assert fake.commit_count == 1


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


@pytest.mark.asyncio
async def test_events_identify_the_destination_endpoint() -> None:
    app = application()
    current_user = user()
    event = WebhookEvent(
        id=uuid4(),
        application_id=app.id,
        idempotency_key="payment-001",
        payload_hash="hash",
        payload={"paid": True},
        headers={},
        received_at=datetime.now(UTC),
    )
    endpoint = Endpoint(
        id=uuid4(),
        application_id=app.id,
        name="n8n",
        url="https://n8n.example.com/webhook",
    )
    delivery = WebhookDelivery(
        id=uuid4(),
        event_id=event.id,
        endpoint_id=endpoint.id,
        status=DeliveryStatus.SUCCEEDED,
        attempt_count=1,
        last_status_code=200,
    )

    class Rows(list[Any]):
        def all(self) -> list[Any]:
            return list(self)

    class EventSession(FakeSession):
        def __init__(self) -> None:
            super().__init__(
                application=app,
                membership=membership(app, current_user, OrganizationRole.OWNER),
            )
            self.rows = [Rows([event]), Rows([delivery]), Rows([endpoint])]

        async def scalars(self, _: object) -> Rows:
            return self.rows.pop(0)

    result = await routes.list_events(app.id, current_user, cast(AsyncSession, EventSession()))

    assert result[0].deliveries[0].endpoint_name == "n8n"
    assert result[0].deliveries[0].endpoint_url == endpoint.url


@pytest.mark.asyncio
async def test_alerts_identify_the_failed_endpoint() -> None:
    app = application()
    current_user = user()
    endpoint = Endpoint(
        id=uuid4(), application_id=app.id, name="Other", url="https://example.com/hook"
    )
    delivery = WebhookDelivery(
        id=uuid4(),
        event_id=uuid4(),
        endpoint_id=endpoint.id,
        status=DeliveryStatus.DEAD,
        attempt_count=5,
    )
    alert = OperationalAlert(
        id=uuid4(),
        application_id=app.id,
        delivery_id=delivery.id,
        message="HTTP 405",
        created_at=datetime.now(UTC),
    )

    class Rows(list[Any]):
        def all(self) -> list[Any]:
            return list(self)

    class AlertSession(FakeSession):
        def __init__(self) -> None:
            super().__init__(
                application=app,
                membership=membership(app, current_user, OrganizationRole.ADMIN),
            )
            event = WebhookEvent(
                id=delivery.event_id,
                application_id=app.id,
                idempotency_key="payment-001",
                payload_hash="hash",
                payload={},
                headers={},
            )
            self.rows = [Rows([alert]), Rows([delivery]), Rows([event]), Rows([endpoint])]

        async def scalars(self, _: object) -> Rows:
            return self.rows.pop(0)

    result = await routes.list_alerts(app.id, current_user, cast(AsyncSession, AlertSession()))

    assert result[0].endpoint_name == "Other"
    assert result[0].endpoint_id == endpoint.id
    assert result[0].event_id == delivery.event_id
    assert result[0].event_idempotency_key == "payment-001"
