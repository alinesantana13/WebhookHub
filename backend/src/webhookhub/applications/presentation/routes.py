from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webhookhub.applications.application.security import (
    UnsafeEndpointError,
    hash_api_key,
    new_api_key,
    validate_endpoint_url,
)
from webhookhub.applications.domain.models import ApiKey, Application, Endpoint
from webhookhub.identity.domain.models import Membership, OrganizationRole, User
from webhookhub.identity.presentation.routes import get_current_user, get_session

router = APIRouter(tags=["applications"])


class NamedRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


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


class EndpointResponse(BaseModel):
    id: UUID
    application_id: UUID
    name: str
    url: str
    enabled: bool
    created_at: datetime


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
    await session.commit()
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


@router.delete("/applications/{application_id}/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    application_id: UUID,
    key_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session, write=True)
    key = await session.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.application_id == application_id)
    )
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await session.commit()


@router.post(
    "/applications/{application_id}/endpoints",
    response_model=EndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint(
    application_id: UUID,
    payload: EndpointRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Endpoint:
    application = await get_application(application_id, session)
    await require_membership(application.organization_id, current_user.id, session, write=True)
    try:
        safe_url = await validate_endpoint_url(payload.url)
    except UnsafeEndpointError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    endpoint = Endpoint(application_id=application.id, name=payload.name, url=safe_url)
    session.add(endpoint)
    await session.commit()
    await session.refresh(endpoint)
    return endpoint


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
