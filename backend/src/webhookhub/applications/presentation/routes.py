from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from webhookhub.applications.application.security import (
    UnsafeEndpointError,
    hash_api_key,
    new_api_key,
    new_signing_secret,
    validate_endpoint_url,
)
from webhookhub.applications.domain.models import (
    ApiKey,
    Application,
    DeliveryStatus,
    Endpoint,
    OperationalAlert,
    WebhookDelivery,
    WebhookEvent,
)
from webhookhub.identity.domain.models import Membership, OrganizationRole, User
from webhookhub.identity.presentation.routes import get_current_user, get_session

router = APIRouter(tags=["applications"])


class NamedRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized


class EndpointRequest(NamedRequest):
    url: str = Field(min_length=1, max_length=2048)


class ApplicationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    created_at: datetime


class ApiKeyCreatedResponse(BaseModel):
    id: UUID
    name: str
    key: str
    prefix: str
    created_at: datetime


class ApiKeyResponse(BaseModel):
    id: UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class EndpointResponse(BaseModel):
    id: UUID
    application_id: UUID
    name: str
    url: str
    enabled: bool
    created_at: datetime


class EndpointCreatedResponse(EndpointResponse):
    signing_secret: str


class DeliveryResponse(BaseModel):
    id: UUID
    endpoint_id: UUID
    endpoint_name: str | None = None
    endpoint_url: str | None = None
    status: DeliveryStatus
    attempt_count: int
    last_status_code: int | None
    last_error: str | None
    delivered_at: datetime | None


class EventResponse(BaseModel):
    id: UUID
    idempotency_key: str
    payload: dict[str, object]
    received_at: datetime
    deliveries: list[DeliveryResponse]


class AlertResponse(BaseModel):
    id: UUID
    delivery_id: UUID
    endpoint_id: UUID | None = None
    endpoint_name: str | None = None
    endpoint_url: str | None = None
    message: str
    created_at: datetime
    acknowledged_at: datetime | None


async def require_membership(
    organization_id: UUID,
    user_id: UUID,
    session: AsyncSession,
    *,
    write: bool = False,
) -> Membership:
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id, Membership.user_id == user_id
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Organization access denied")
    if write and membership.role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Administrator role required")
    return membership


async def get_application(application_id: UUID, session: AsyncSession) -> Application:
    application = await session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.post(
    "/organizations/{organization_id}/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application(
    organization_id: UUID,
    payload: NamedRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Application:
    await require_membership(organization_id, current_user.id, session, write=True)
    application = Application(organization_id=organization_id, name=payload.name)
    session.add(application)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Application name already exists in this organization",
        ) from error
    await session.refresh(application)
    return application


@router.get(
    "/organizations/{organization_id}/applications", response_model=list[ApplicationResponse]
)
async def list_applications(
    organization_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Application]:
    await require_membership(organization_id, current_user.id, session)
    return list(
        (
            await session.scalars(
                select(Application)
                .where(Application.organization_id == organization_id)
                .order_by(Application.created_at)
            )
        ).all()
    )


@router.delete("/applications/{application_id}", status_code=204)
async def delete_application(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session, write=True)
    await session.delete(application)
    await session.commit()


@router.post(
    "/applications/{application_id}/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    application_id: UUID,
    payload: NamedRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKeyCreatedResponse:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session, write=True)
    raw_key = new_api_key()
    key = ApiKey(
        application_id=application.id,
        name=payload.name,
        key_prefix=raw_key[:12],
        key_hash=hash_api_key(raw_key),
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return ApiKeyCreatedResponse(
        id=key.id, name=key.name, key=raw_key, prefix=key.key_prefix, created_at=key.created_at
    )


async def get_api_key(application_id: UUID, key_id: UUID, session: AsyncSession) -> ApiKey:
    key = await session.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.application_id == application_id)
    )
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return key


@router.post("/applications/{application_id}/api-keys/{key_id}/revoke", status_code=204)
async def revoke_api_key(
    application_id: UUID,
    key_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session, write=True)
    key = await get_api_key(application_id, key_id, session)
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await session.commit()


@router.delete("/applications/{application_id}/api-keys/{key_id}", status_code=204)
async def delete_api_key(
    application_id: UUID,
    key_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session, write=True)
    key = await get_api_key(application_id, key_id, session)
    await session.delete(key)
    await session.commit()


@router.get("/applications/{application_id}/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ApiKeyResponse]:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session)
    keys = (
        await session.scalars(
            select(ApiKey)
            .where(ApiKey.application_id == application_id)
            .order_by(ApiKey.created_at.desc())
        )
    ).all()
    return [
        ApiKeyResponse(
            id=key.id,
            name=key.name,
            prefix=key.key_prefix,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            revoked_at=key.revoked_at,
        )
        for key in keys
    ]


@router.post(
    "/applications/{application_id}/endpoints",
    response_model=EndpointCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint(
    application_id: UUID,
    payload: EndpointRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EndpointCreatedResponse:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session, write=True)
    try:
        safe_url = await validate_endpoint_url(payload.url)
    except UnsafeEndpointError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    endpoint = Endpoint(
        application_id=application.id,
        name=payload.name,
        url=safe_url,
        signing_secret=new_signing_secret(),
        enabled=True,
    )
    session.add(endpoint)
    await session.commit()
    await session.refresh(endpoint)
    return EndpointCreatedResponse(
        id=endpoint.id,
        application_id=endpoint.application_id,
        name=endpoint.name,
        url=endpoint.url,
        enabled=endpoint.enabled,
        created_at=endpoint.created_at,
        signing_secret=endpoint.signing_secret,
    )


@router.get("/applications/{application_id}/endpoints", response_model=list[EndpointResponse])
async def list_endpoints(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Endpoint]:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session)
    return list(
        (
            await session.scalars(
                select(Endpoint)
                .where(Endpoint.application_id == application_id)
                .order_by(Endpoint.created_at)
            )
        ).all()
    )


@router.get("/applications/{application_id}/events", response_model=list[EventResponse])
async def list_events(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 50,
) -> list[EventResponse]:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session)
    bounded_limit = max(1, min(limit, 100))
    events = (
        await session.scalars(
            select(WebhookEvent)
            .where(WebhookEvent.application_id == application_id)
            .order_by(WebhookEvent.received_at.desc())
            .limit(bounded_limit)
        )
    ).all()
    if not events:
        return []
    deliveries = (
        await session.scalars(
            select(WebhookDelivery).where(
                WebhookDelivery.event_id.in_([event.id for event in events])
            )
        )
    ).all()
    endpoints = (
        await session.scalars(
            select(Endpoint).where(
                Endpoint.id.in_({delivery.endpoint_id for delivery in deliveries})
            )
        )
    ).all()
    endpoints_by_id = {endpoint.id: endpoint for endpoint in endpoints}
    by_event: dict[UUID, list[DeliveryResponse]] = {}
    for delivery in deliveries:
        endpoint = endpoints_by_id.get(delivery.endpoint_id)
        by_event.setdefault(delivery.event_id, []).append(
            DeliveryResponse(
                id=delivery.id,
                endpoint_id=delivery.endpoint_id,
                endpoint_name=endpoint.name if endpoint else None,
                endpoint_url=endpoint.url if endpoint else None,
                status=delivery.status,
                attempt_count=delivery.attempt_count,
                last_status_code=delivery.last_status_code,
                last_error=delivery.last_error,
                delivered_at=delivery.delivered_at,
            )
        )
    return [
        EventResponse(
            id=event.id,
            idempotency_key=event.idempotency_key,
            payload=event.payload,
            received_at=event.received_at,
            deliveries=by_event.get(event.id, []),
        )
        for event in events
    ]


@router.post(
    "/applications/{application_id}/deliveries/{delivery_id}/replay",
    response_model=DeliveryResponse,
)
async def replay_delivery(
    application_id: UUID,
    delivery_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WebhookDelivery:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session, write=True)
    delivery = await session.scalar(
        select(WebhookDelivery)
        .join(WebhookEvent, WebhookEvent.id == WebhookDelivery.event_id)
        .where(
            WebhookDelivery.id == delivery_id,
            WebhookEvent.application_id == application_id,
        )
        .with_for_update()
    )
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    delivery.status = DeliveryStatus.PENDING
    delivery.attempt_count = 0
    delivery.next_attempt_at = datetime.now(UTC)
    delivery.last_status_code = None
    delivery.last_error = None
    delivery.delivered_at = None
    await session.commit()
    await session.refresh(delivery)
    return delivery


@router.get("/applications/{application_id}/alerts", response_model=list[AlertResponse])
async def list_alerts(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AlertResponse]:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session)
    alerts = list(
        await session.scalars(
            select(OperationalAlert)
            .where(OperationalAlert.application_id == application_id)
            .order_by(OperationalAlert.created_at.desc())
            .limit(100)
        )
    )
    if not alerts:
        return []
    deliveries = (
        await session.scalars(
            select(WebhookDelivery).where(
                WebhookDelivery.id.in_([alert.delivery_id for alert in alerts])
            )
        )
    ).all()
    deliveries_by_id = {delivery.id: delivery for delivery in deliveries}
    endpoints = (
        await session.scalars(
            select(Endpoint).where(
                Endpoint.id.in_({delivery.endpoint_id for delivery in deliveries})
            )
        )
    ).all()
    endpoints_by_id = {endpoint.id: endpoint for endpoint in endpoints}
    return [
        AlertResponse(
            id=alert.id,
            delivery_id=alert.delivery_id,
            endpoint_id=delivery.endpoint_id if delivery else None,
            endpoint_name=endpoint.name if endpoint else None,
            endpoint_url=endpoint.url if endpoint else None,
            message=alert.message,
            created_at=alert.created_at,
            acknowledged_at=alert.acknowledged_at,
        )
        for alert in alerts
        for delivery in [deliveries_by_id.get(alert.delivery_id)]
        for endpoint in [endpoints_by_id.get(delivery.endpoint_id) if delivery else None]
    ]


@router.post(
    "/applications/{application_id}/alerts/{alert_id}/acknowledge",
    response_model=AlertResponse,
)
async def acknowledge_alert(
    application_id: UUID,
    alert_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OperationalAlert:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session, write=True)
    alert = await session.scalar(
        select(OperationalAlert).where(
            OperationalAlert.id == alert_id,
            OperationalAlert.application_id == application_id,
        )
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.acknowledged_at is None:
        alert.acknowledged_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(alert)
    return alert
