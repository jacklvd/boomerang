"""Shared fixtures.

Every test that touches ``app.bedrock`` runs against a known environment: the module reads
configuration through ``os.getenv`` at call time, so a leaked variable from the developer's
shell would otherwise change the outcome.
"""

import pytest

from app import bedrock

BEDROCK_VARS = ("BEDROCK_MODEL", "BEDROCK_MODEL_PARSE", "BEDROCK_MODEL_ACTION", "AWS_REGION")


@pytest.fixture(autouse=True)
def clean_bedrock_env(monkeypatch):
    """Remove every Bedrock variable so each test states the configuration it needs."""
    for name in BEDROCK_VARS:
        monkeypatch.delenv(name, raising=False)
    bedrock.client.cache_clear()
    yield
    bedrock.client.cache_clear()
