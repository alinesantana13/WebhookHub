from redis.asyncio import Redis
from redis.exceptions import RedisError


class CacheUnavailableError(RuntimeError):
    """Raised when Redis cannot serve a readiness probe."""


class RedisCache:
    def __init__(self, dsn: str) -> None:
        self.client = Redis.from_url(dsn, decode_responses=True)

    async def ping(self) -> None:
        try:
            await self.client.ping()
        except (RedisError, OSError) as error:
            raise CacheUnavailableError from error

    async def close(self) -> None:
        await self.client.aclose()
