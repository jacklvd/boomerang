"""Explicit SQLAlchemy async engine and session construction."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_async_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Build a PostgreSQL async engine without opening a connection."""
    if not database_url.startswith("postgresql+psycopg://"):
        msg = "database_url must use the postgresql+psycopg driver"
        raise ValueError(msg)
    return create_async_engine(database_url, echo=echo, pool_pre_ping=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build sessions whose loaded state remains usable after a commit."""
    return async_sessionmaker(engine, expire_on_commit=False)
