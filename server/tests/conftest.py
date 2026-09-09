"""Shared fixtures.

Every test that touches ``app.bedrock`` runs against a known environment: the module reads
configuration through ``os.getenv`` at call time, so a leaked variable from the developer's
shell would otherwise change the outcome.
"""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app import bedrock
from app.db import models as _models  # noqa: F401 - registering mapped tables is the fixture setup.
from app.db.base import Base
from app.db.session import build_async_engine

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
