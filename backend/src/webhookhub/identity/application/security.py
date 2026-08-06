from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash


class InvalidAccessTokenError(ValueError):
    """Raised when an access token cannot be trusted."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    expires_at: datetime


class TokenService:
    def __init__(self, secret_key: str, access_ttl_minutes: int) -> None:
        self._secret_key = secret_key
        self._access_ttl = timedelta(minutes=access_ttl_minutes)

    def create_access_token(self, user_id: UUID) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {"sub": str(user_id), "iat": now, "exp": now + self._access_ttl, "type": "access"},
            self._secret_key,
            algorithm="HS256",
        )

    def decode_access_token(self, token: str) -> AccessClaims:
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=["HS256"])
            if payload.get("type") != "access":
                raise InvalidAccessTokenError
            return AccessClaims(UUID(payload["sub"]), datetime.fromtimestamp(payload["exp"], UTC))
        except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise InvalidAccessTokenError from error


password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def new_refresh_token() -> str:
    return token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()
