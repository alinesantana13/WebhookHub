import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from webhookhub.bootstrap.config import Settings
from webhookhub.identity.application.security import (
    InvalidAccessTokenError,
    TokenService,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from webhookhub.identity.domain.models import (
    Membership,
    Organization,
    OrganizationRole,
    Session,
    User,
)
from webhookhub.shared.infrastructure.database import Database

router = APIRouter(prefix="/auth", tags=["identity"])
organizations_router = APIRouter(prefix="/organizations", tags=["organizations"])
bearer = HTTPBearer(auto_error=False)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    organization_name: str = Field(min_length=1, max_length=120)
    organization_slug: str = Field(
        min_length=3, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("invalid email address")
        return normalized


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class OrganizationSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    role: OrganizationRole


class CurrentUserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    organizations: list[OrganizationSummary]


class MemberResponse(BaseModel):
    user_id: UUID
    email: str
    name: str
    role: OrganizationRole


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    database: Database = request.app.state.database
    async for session in database.get_session():
        yield session


def get_token_service(settings: Annotated[Settings, Depends(get_settings)]) -> TokenService:
    return TokenService(settings.auth_secret_key, settings.access_token_ttl_minutes)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = tokens.decode_access_token(credentials.credentials)
    except InvalidAccessTokenError as error:
        raise unauthorized from error
    user = await session.get(User, claims.user_id)
    if user is None:
        raise unauthorized
    return user


async def issue_tokens(
    user_id: UUID,
    session: AsyncSession,
    settings: Settings,
    tokens: TokenService,
) -> TokenResponse:
    refresh_token = new_refresh_token()
    session.add(
        Session(
            user_id=user_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    await session.flush()
    return TokenResponse(
        access_token=tokens.create_access_token(user_id), refresh_token=refresh_token
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenResponse:
    user = User(
        email=payload.email, password_hash=hash_password(payload.password), name=payload.name
    )
    organization = Organization(name=payload.organization_name, slug=payload.organization_slug)
    session.add_all([user, organization])
    try:
        await session.flush()
        session.add(
            Membership(
                user_id=user.id,
                organization_id=organization.id,
                role=OrganizationRole.OWNER,
            )
        )
        response = await issue_tokens(user.id, session, settings, tokens)
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Email or organization slug already exists"
        ) from error
    return response


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenResponse:
    email = payload.email.strip().casefold()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    response = await issue_tokens(user.id, session, settings, tokens)
    await session.commit()
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenResponse:
    current = await session.scalar(
        select(Session)
        .where(Session.token_hash == hash_refresh_token(payload.refresh_token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if current is None or current.expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if current.revoked_at is not None:
        await session.execute(
            update(Session)
            .where(Session.user_id == current.user_id, Session.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="Refresh token reuse detected")

    current.revoked_at = now
    response = await issue_tokens(current.user_id, session, settings, tokens)
    replacement = await session.scalar(
        select(Session).where(Session.token_hash == hash_refresh_token(response.refresh_token))
    )
    current.replaced_by_id = replacement.id if replacement else None
    await session.commit()
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    current = await session.scalar(
        select(Session).where(Session.token_hash == hash_refresh_token(payload.refresh_token))
    )
    if current is not None and current.revoked_at is None:
        current.revoked_at = datetime.now(UTC)
        await session.commit()


@router.get("/me", response_model=CurrentUserResponse)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUserResponse:
    memberships = (
        await session.scalars(
            select(Membership)
            .where(Membership.user_id == current_user.id)
            .options(selectinload(Membership.organization))
        )
    ).all()
    return CurrentUserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        organizations=[
            OrganizationSummary(
                id=item.organization.id,
                name=item.organization.name,
                slug=item.organization.slug,
                role=item.role,
            )
            for item in memberships
        ],
    )


@organizations_router.get("/{organization_id}/members", response_model=list[MemberResponse])
async def list_members(
    organization_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MemberResponse]:
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == current_user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Organization access denied")
    members = (
        await session.scalars(
            select(Membership)
            .where(Membership.organization_id == organization_id)
            .options(selectinload(Membership.user))
        )
    ).all()
    return [
        MemberResponse(
            user_id=item.user.id, email=item.user.email, name=item.user.name, role=item.role
        )
        for item in members
    ]
