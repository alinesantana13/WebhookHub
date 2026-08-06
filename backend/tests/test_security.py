from datetime import UTC, datetime
from uuid import uuid4

import pytest

from webhookhub.identity.application.security import (
    InvalidAccessTokenError,
    TokenService,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)


def test_password_is_hashed_and_verified() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    service = TokenService("test-secret-that-is-at-least-32-bytes", access_ttl_minutes=15)

    claims = service.decode_access_token(service.create_access_token(user_id))

    assert claims.user_id == user_id
    assert claims.expires_at > datetime.now(UTC)


def test_invalid_access_token_is_rejected() -> None:
    with pytest.raises(InvalidAccessTokenError):
        TokenService("test-secret-that-is-at-least-32-bytes", 15).decode_access_token("not-a-token")


def test_refresh_tokens_are_random_and_only_stored_as_hashes() -> None:
    first = new_refresh_token()
    second = new_refresh_token()

    assert first != second
    assert hash_refresh_token(first) != first
    assert len(hash_refresh_token(first)) == 64
