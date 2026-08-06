from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import MetaData, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class DatabaseUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot serve a readiness probe."""


class Database:
    def __init__(self, dsn: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(
            dsn,
            echo=echo,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def ping(self) -> None:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError) as error:
            raise DatabaseUnavailableError from error

    async def dispose(self) -> None:
        await self.engine.dispose()
