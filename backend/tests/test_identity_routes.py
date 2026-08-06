from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from webhookhub.bootstrap.config import Settings
from webhookhub.identity.application.security import TokenService
from webhookhub.identity.domain.models import Session, User
from webhookhub.identity.presentation.routes import (
    RegisterRequest,
    get_current_user,
    get_token_service,
    issue_tokens,
)


class FakeSession:
    def __init__(self, user: User | None = None) -> None:
        self.user = user
        self.added: list[Any] = []
        self.flush_count = 0

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def get(self, model: type[User], identifier: object) -> User | None:
        assert model is User
        return self.user if self.user and self.user.id == identifier else None


def test_token_service_uses_application_settings() -> None:
    settings = Settings(environment="test", cors_origins=[], auth_secret_key="x" * 32)

    token = get_token_service(settings).create_access_token(uuid4())

    assert token


def test_register_request_normalizes_email() -> None:
    request = RegisterRequest(
        email="  Owner@Example.COM ",
        password="a-secure-password",  # noqa: S106
        name="Owner",
        organization_name="Acme",
        organization_slug="acme",
    )

    assert request.email == "owner@example.com"


def test_register_request_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="invalid",
            password="a-secure-password",  # noqa: S106
            name="Owner",
            organization_name="Acme",
            organization_slug="acme",
        )


@pytest.mark.asyncio
async def test_issue_tokens_persists_hashed_refresh_token() -> None:
    user_id = uuid4()
    fake = FakeSession()
    session = cast(AsyncSession, fake)
    settings = Settings(environment="test", cors_origins=[])

    response = await issue_tokens(user_id, session, settings, TokenService("x" * 32, 15))

    stored = cast(Session, fake.added[0])
    assert response.access_token
    assert response.refresh_token != stored.token_hash
    assert stored.user_id == user_id
    assert fake.flush_count == 1


@pytest.mark.asyncio
async def test_current_user_is_loaded_from_valid_token() -> None:
    user = User(
        id=uuid4(), email="owner@example.com", password_hash="hash", name="Owner"  # noqa: S106
    )
    tokens = TokenService("x" * 32, 15)
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=tokens.create_access_token(user.id)
    )

    current = await get_current_user(
        credentials, cast(AsyncSession, FakeSession(user)), tokens
    )

    assert current is user


@pytest.mark.asyncio
async def test_current_user_requires_credentials() -> None:
    with pytest.raises(HTTPException) as raised:
        await get_current_user(
            None, cast(AsyncSession, FakeSession()), TokenService("x" * 32, 15)
        )

    assert raised.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_rejects_invalid_token() -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid")

    with pytest.raises(HTTPException) as raised:
        await get_current_user(
            credentials,
            cast(AsyncSession, FakeSession()),
            TokenService("x" * 32, 15),
        )

    assert raised.value.status_code == 401
