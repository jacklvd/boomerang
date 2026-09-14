"""Tests for ``GET /v1/me`` and the request-to-repository plumbing that serves it.

Two things are under test here and they are deliberately in one file, because the route
is the thing that proves the plumbing: the dependency chain that turns an authenticated
principal into an account-scoped repository (``app.api.deps``), and the first route built
on it (``app.routes.me``).

Nothing here needs PostgreSQL. The chain is exercised against a stand-in session that
records the identity each read asks for, which is what makes the account-scoping
assertions structural rather than a matter of trusting the query.
"""

from datetime import UTC, datetime
from typing import Self

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.api.auth import AccountScope, get_account_scope
from app.api.errors import install_error_handling
from app.db.base import Base
from app.db.models import AccountRow
from app.db.session import build_session_factory
from app.main import app as production_app
from app.routes import api_router


class FakeSession:
    """Stands in for the async session the factory hands out.

    It answers the one call ``ScopedRepository.get_account`` makes and records the
    identity it was asked for, so a test can assert *which* account was read rather than
    only what came back.
    """

    def __init__(self, account: AccountRow | None) -> None:
        self._account = account
        self.requested_identities: list[object] = []
        self.closed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc_info: object) -> bool:
        self.closed = True
        return False

    async def get(self, entity: object, identity: object, **_kwargs: object) -> AccountRow | None:
        self.requested_identities.append((entity, identity))
        return self._account


class FakeSessionFactory:
    """Stands in for the session factory the lifespan installs on ``app.state``."""

    def __init__(self, account: AccountRow | None) -> None:
        self._account = account
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = FakeSession(self._account)
        self.sessions.append(session)
        return session


def _account_row() -> AccountRow:
    return AccountRow(
        id="acct_known",
        google_subject="google-subject-must-never-be-exposed",
        email="sam@example.com",
        display_name="Sam",
        avatar_url="https://example.com/avatar.png",
    )


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


def test_me_returns_the_profile_of_the_account_the_principal_resolved_to(api_app, sign_in):
    # The full real chain minus the database driver: the auth override supplies the
    # account, deps opens a session from the factory on app.state, and the real
    # ScopedRepository reads through it.
    sign_in("acct_known")
    factory = FakeSessionFactory(_account_row())
    api_app.state.session_factory = factory

    response = TestClient(api_app).get("/v1/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": "acct_known",
        "email": "sam@example.com",
        "display_name": "Sam",
        "avatar_url": "https://example.com/avatar.png",
    }
    assert factory.sessions[0].requested_identities == [(AccountRow, "acct_known")]


def test_me_never_exposes_the_google_subject(api_app, sign_in):
    sign_in("acct_known")
    api_app.state.session_factory = FakeSessionFactory(_account_row())

    response = TestClient(api_app).get("/v1/me")

    assert "google_subject" not in response.json()
    assert "google-subject-must-never-be-exposed" not in response.text


def test_me_allows_the_nullable_profile_fields_to_be_null(api_app, sign_in):
    sign_in("acct_known")
    api_app.state.session_factory = FakeSessionFactory(
        AccountRow(
            id="acct_known",
            google_subject="google-subject",
            email=None,
            display_name=None,
            avatar_url=None,
        )
    )

    response = TestClient(api_app).get("/v1/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": "acct_known",
        "email": None,
        "display_name": None,
        "avatar_url": None,
    }


def test_me_is_not_found_when_the_scoped_account_row_is_absent(api_app, sign_in):
    # An absent row and a row belonging to another account are the same thing to the
    # repository — both come back as None — and both must look identical on the wire.
    sign_in("acct_known")
    api_app.state.session_factory = FakeSessionFactory(None)

    response = TestClient(api_app).get("/v1/me")

    assert response.status_code == 404
    body = response.json()
    assert body["reason"] == "not_found"
    assert body["details"] is None


def test_me_serves_from_a_stand_in_repository_when_a_test_only_cares_about_the_handler(
    api_app, sign_in, serve_repository
):
    # Proves the fixture the remaining route modules will use: override the repository
    # dependency itself, and the handler runs with no session machinery at all.
    class StubRepository:
        async def get_account(self) -> AccountRow:
            return _account_row()

    sign_in("acct_known")
    serve_repository(StubRepository())

    response = TestClient(api_app).get("/v1/me")

    assert response.status_code == 200
    assert response.json()["id"] == "acct_known"


# ---------------------------------------------------------------------------
# Account scope comes from the principal and from nowhere else
# ---------------------------------------------------------------------------


def test_me_is_unauthenticated_without_a_principal(api_app):
    response = TestClient(api_app).get("/v1/me")

    assert response.status_code == 401
    body = response.json()
    assert body["reason"] == "unauthenticated"
    assert isinstance(body["message"], str)
    assert body["message"]
    assert body["request_id"].startswith("req_")
    assert body["details"] == {"cause": "authentication_not_configured"}
    assert set(body) == {"reason", "message", "request_id", "details"}


def test_me_never_opens_a_session_for_an_unauthenticated_request(api_app):
    # The account scope is resolved before the repository dependency runs, so a request
    # that cannot be authenticated never reaches the database at all.
    factory = FakeSessionFactory(_account_row())
    api_app.state.session_factory = factory

    response = TestClient(api_app).get("/v1/me")

    assert response.status_code == 401
    assert factory.sessions == []


def test_me_ignores_an_account_id_supplied_by_the_client(api_app, sign_in):
    # The exact bug the scoping seam exists to prevent: a caller naming the account it
    # wants. Query string, header and cookie all carry an attacker-chosen id; the reply
    # must be the signed-in account, and the read must have asked for that id only.
    sign_in("acct_known")
    factory = FakeSessionFactory(_account_row())
    api_app.state.session_factory = factory

    client = TestClient(api_app)
    client.cookies.set("account_id", "acct_attacker")
    response = client.get(
        "/v1/me",
        params={"account_id": "acct_attacker", "sub": "attacker"},
        headers={"X-Account-Id": "acct_attacker"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "acct_known"
    assert factory.sessions[0].requested_identities == [(AccountRow, "acct_known")]
    assert "acct_attacker" not in response.text


def test_the_repository_is_scoped_to_whichever_account_the_principal_carries(api_app, sign_in):
    # Same route, a different principal, and the read follows the principal.
    sign_in("acct_someone_else")
    factory = FakeSessionFactory(
        AccountRow(
            id="acct_someone_else",
            google_subject="google-subject",
            email=None,
            display_name=None,
            avatar_url=None,
        )
    )
    api_app.state.session_factory = factory

    response = TestClient(api_app).get("/v1/me")

    assert response.json()["id"] == "acct_someone_else"
    assert factory.sessions[0].requested_identities == [(AccountRow, "acct_someone_else")]


# ---------------------------------------------------------------------------
# The per-request session
# ---------------------------------------------------------------------------


def test_the_request_session_is_closed_after_the_response(api_app, sign_in):
    sign_in("acct_known")
    factory = FakeSessionFactory(_account_row())
    api_app.state.session_factory = factory

    TestClient(api_app).get("/v1/me")

    assert len(factory.sessions) == 1
    assert factory.sessions[0].closed


def test_each_request_borrows_its_own_session(api_app, sign_in):
    sign_in("acct_known")
    factory = FakeSessionFactory(_account_row())
    api_app.state.session_factory = factory

    client = TestClient(api_app)
    client.get("/v1/me")
    client.get("/v1/me")

    assert len(factory.sessions) == 2
    assert factory.sessions[0] is not factory.sessions[1]


def test_a_request_without_lifespan_startup_fails_loudly_rather_than_silently(api_app, sign_in):
    # No factory on app.state means lifespan startup never ran. The honest answer is a
    # server error; building an engine per request here would hide a broken deployment.
    sign_in("acct_known")

    response = TestClient(api_app, raise_server_exceptions=False).get("/v1/me")

    assert response.status_code == 500
    assert response.json()["reason"] == "internal_error"


# ---------------------------------------------------------------------------
# Startup configuration: no default, no silent fallback
# ---------------------------------------------------------------------------


def test_the_database_url_has_no_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        deps._require_database_url()  # noqa: SLF001 - the failure mode is the point


def test_startup_fails_when_the_database_is_unconfigured(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"), TestClient(production_app):
        pass  # pragma: no cover — the context manager raises on entry


def test_startup_rejects_a_database_url_that_is_not_the_async_psycopg_driver(monkeypatch):
    # A synchronous DSN would fail on the first query inside a request instead of here.
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@127.0.0.1:5432/boomerang")

    with pytest.raises(ValueError, match="postgresql\\+psycopg"), TestClient(production_app):
        pass  # pragma: no cover — the context manager raises on entry


def test_lifespan_builds_one_session_factory_and_releases_it_on_shutdown(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL", "us.anthropic.shared")

    with TestClient(production_app):
        during_startup = production_app.state.session_factory
        assert during_startup is not None
        # Still the same object on a second read: built once per process, not per request.
        assert production_app.state.session_factory is during_startup

    assert production_app.state.session_factory is None


# ---------------------------------------------------------------------------
# Mounting
# ---------------------------------------------------------------------------


def test_the_version_prefix_lives_on_the_aggregator_router():
    # Route modules declare paths relative to the version; the prefix is applied once.
    assert api_router.prefix == "/v1"


def test_the_production_app_mounts_the_versioned_router():
    assert "/v1/me" in production_app.openapi()["paths"]


def test_health_stays_outside_the_versioned_api():
    paths = production_app.openapi()["paths"]

    assert "/health" in paths
    assert "/v1/health" not in paths


def test_the_scope_dependency_is_what_the_override_replaces(api_app):
    # Guards the injection point the rest of these tests (and the next route modules)
    # rely on: overriding the auth dependency is what changes who the caller is.
    api_app.dependency_overrides[get_account_scope] = lambda: AccountScope(account_id="acct_known")
    api_app.state.session_factory = FakeSessionFactory(_account_row())

    assert TestClient(api_app).get("/v1/me").status_code == 200


def test_the_router_can_be_mounted_on_any_app_without_further_wiring(api_app):
    # The aggregator is self-contained: one include_router call is the whole mounting
    # contract, which is why app.main never needs editing when a route module is added.
    fresh = FastAPI()
    fresh.include_router(api_router)

    assert "/v1/me" in fresh.openapi()["paths"]


# ---------------------------------------------------------------------------
# The same chain against real PostgreSQL
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_the_chain_serves_the_profile_from_postgresql(database_engine):
    # The Docker-free tests above stand in for the driver. This one is the end-to-end
    # proof that the DSN the lifespan validates, the factory it builds, the session a
    # request borrows and the scoped read all fit together against a real database.
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    now = datetime.now(UTC)
    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add(
            AccountRow(
                id="acct_integration",
                google_subject="google-subject-must-never-be-exposed",
                email="sam@example.com",
                display_name="Sam",
                avatar_url="https://example.com/avatar.png",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AccountRow(
                id="acct_other",
                google_subject="another-google-subject",
                email="other@example.com",
                display_name="Other",
                avatar_url=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    app = FastAPI()
    install_error_handling(app)
    app.include_router(api_router)
    app.state.session_factory = session_factory
    app.dependency_overrides[get_account_scope] = lambda: AccountScope(
        account_id="acct_integration"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/me", params={"account_id": "acct_other"})

    assert response.status_code == 200
    assert response.json() == {
        "id": "acct_integration",
        "email": "sam@example.com",
        "display_name": "Sam",
        "avatar_url": "https://example.com/avatar.png",
    }
    assert "google-subject-must-never-be-exposed" not in response.text
