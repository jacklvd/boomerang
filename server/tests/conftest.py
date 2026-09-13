"""Shared fixtures.

Every test that touches ``app.bedrock`` runs against a known environment: the module reads
configuration through ``os.getenv`` at call time, so a leaked variable from the developer's
shell would otherwise change the outcome.
"""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app import bedrock
from app.api.auth import AccountScope, get_account_scope
from app.api.deps import get_scoped_repository
from app.api.errors import install_error_handling
from app.db import models as _models  # noqa: F401 - registering mapped tables is the fixture setup.
from app.db.base import Base
from app.db.session import build_async_engine
from app.routes import api_router

BEDROCK_VARS = ("BEDROCK_MODEL", "BEDROCK_MODEL_PARSE", "BEDROCK_MODEL_ACTION", "AWS_REGION")


@pytest.fixture(autouse=True)
def clean_bedrock_env(monkeypatch):
    """Remove every Bedrock variable so each test states the configuration it needs."""
    for name in BEDROCK_VARS:
        monkeypatch.delenv(name, raising=False)
    bedrock.client.cache_clear()
    yield
    bedrock.client.cache_clear()


@pytest.fixture
async def database_engine() -> AsyncIterator[AsyncEngine]:
    """Provide a PostgreSQL engine and defensively remove the ORM schema after use."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    engine = build_async_engine(database_url)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


# ---------------------------------------------------------------------------
# /v1 route fixtures
#
# Route tests run against a throwaway app carrying the real aggregator router and the
# real error envelope, with no lifespan and no database. Injection is FastAPI's own
# dependency-override mechanism, scoped to that app instance — nothing in ``app/`` ever
# installs an override, so none of this exists in a running process.
# ---------------------------------------------------------------------------

DATABASE_URL_FOR_UNIT_TESTS = "postgresql+psycopg://boomerang:boomerang@127.0.0.1:5432/boomerang"


@pytest.fixture(autouse=True)
def stub_database_url(monkeypatch):
    """Pin DATABASE_URL to a DSN that is never connected to, for the same reason as above.

    The value is read through ``os.getenv`` at startup, so a variable exported in the
    developer's shell would otherwise decide what a test proves. Engines built from this
    URL are constructed lazily and the Docker-free suite never opens a connection. A test
    that needs the variable absent or malformed sets that itself.
    """
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL_FOR_UNIT_TESTS)


@pytest.fixture
def api_app() -> Iterator[FastAPI]:
    """A throwaway app mounting the real ``/v1`` router and the real error envelope."""
    app = FastAPI()
    install_error_handling(app)
    app.include_router(api_router)
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def sign_in(api_app):
    """Return a callable injecting a known account scope into ``api_app``."""

    def _sign_in(account_id: str = "acct_test") -> str:
        api_app.dependency_overrides[get_account_scope] = lambda: AccountScope(
            account_id=account_id
        )
        return account_id

    return _sign_in


@pytest.fixture
def serve_repository(api_app):
    """Return a callable serving ``api_app``'s routes from a stand-in repository.

    Use it when a route test cares about the handler rather than about the repository:
    the object passed in only has to answer the repository methods that route calls.
    """

    def _serve_repository(repository: object) -> object:
        api_app.dependency_overrides[get_scoped_repository] = lambda: repository
        return repository

    return _serve_repository
