from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WEBHOOKHUB_",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_host: str = "0.0.0.0"  # noqa: S104 - required for container networking
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[AnyHttpUrl] = Field(default_factory=list)
    postgres_dsn: str = "postgresql+asyncpg://webhookhub:webhookhub@localhost:5432/webhookhub"
    auth_secret_key: str = "local-development-secret-change-me"  # noqa: S105
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=365)
    redis_dsn: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: list[str] = Field(default_factory=lambda: ["localhost:9092"])

    @property
    def docs_enabled(self) -> bool:
        return self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
