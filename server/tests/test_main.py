"""The app boots only when the model is configured — that is the point of the lifespan check."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ok(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_fails_when_the_model_is_unconfigured():
    # dev-note: this is the whole reason verify_config lives in the lifespan. A cold start
    # must fail loudly rather than deferring the error to a user's first parse.
    with pytest.raises(RuntimeError, match="BEDROCK_MODEL is not set"), TestClient(app):
        pass  # pragma: no cover — the context manager raises on entry


def test_health_does_not_require_a_lifespan(monkeypatch):
    # Without the context manager TestClient skips lifespan, so the route itself is proven
    # to do no I/O and depend on no cached startup state.
    monkeypatch.delenv("BEDROCK_MODEL", raising=False)
    assert TestClient(app).get("/health").json() == {"status": "ok"}
