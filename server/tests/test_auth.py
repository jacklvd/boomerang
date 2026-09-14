"""Tests for the account authentication seam in ``app.api.auth``.

No authentication scheme is decided yet, so these tests prove three things about the
seam itself rather than about any particular scheme: the unconfigured production path
fails closed no matter what, the structural narrowing that makes the account id
unreachable from a path/query/body actually holds, and the FastAPI dependency-override
mechanism is the (test-only) way to inject a known account.
"""

import dataclasses
import inspect
import typing

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth as auth_module
from app.api.auth import (
    AccountScope,
    AccountScopeDep,
    AuthenticationInputs,
    _resolve_account_id,
    get_account_scope,
)
from app.api.errors import install_error_handling


def _build_app() -> FastAPI:
    """A throwaway app with one route that depends on the real, unconfigured seam."""
    app = FastAPI()
    install_error_handling(app)

    @app.get("/whoami")
    async def whoami(account: AccountScopeDep) -> dict[str, str]:
        return {"account_id": account.account_id}

    return app


def test_unconfigured_seam_fails_closed():
    response = TestClient(_build_app()).get("/whoami")

    assert response.status_code == 401
    body = response.json()
    assert body["reason"] == "unauthenticated"
    assert body["details"] == {"cause": "authentication_not_configured"}


def test_fail_closed_holds_regardless_of_path_or_query_content():
    # A body/path/query-derived account id would be the exact bug this seam prevents;
    # prove that stuffing account-shaped values into the query string changes nothing.
    response = TestClient(_build_app()).get(
        "/whoami", params={"account_id": "acct_attacker", "sub": "attacker"}
    )

    assert response.status_code == 401


def test_no_environment_variable_bypasses_authentication(monkeypatch):
    # There must be no "turn auth off for dev" switch. Try a few plausible-looking ones.
    for name, value in (
        ("AUTH_DISABLED", "1"),
        ("SKIP_AUTH", "true"),
        ("DEBUG", "1"),
        ("ENVIRONMENT", "development"),
        ("BOOMERANG_ACCOUNT_ID", "acct_default"),
    ):
        monkeypatch.setenv(name, value)

    response = TestClient(_build_app()).get("/whoami")

    assert response.status_code == 401


def test_account_scope_account_id_is_a_plain_str_never_optional():
    hints = typing.get_type_hints(AccountScope)

    assert hints["account_id"] is str


def test_account_scope_has_no_service_principal_escape_hatch():
    field_names = {field.name for field in dataclasses.fields(AccountScope)}

    assert field_names == {"account_id"}


def test_authentication_inputs_exposes_only_headers_and_cookies():
    field_names = {field.name for field in dataclasses.fields(AuthenticationInputs)}

    assert field_names == {"headers", "cookies"}


def test_the_seam_function_can_only_see_authentication_inputs():
    # The seam's signature is the structural guarantee: whatever scheme gets written in
    # here, it is handed an object with no path/query/body accessor to reach for.
    sig = inspect.signature(_resolve_account_id)
    hints = typing.get_type_hints(_resolve_account_id)

    assert list(sig.parameters) == ["inputs"]
    assert hints["inputs"] is AuthenticationInputs
    assert hints["return"] is str


def test_get_account_scope_is_the_async_dependency_route_modules_should_use():
    assert inspect.iscoroutinefunction(get_account_scope)


async def test_get_account_scope_wraps_a_resolved_account_id_in_an_account_scope(monkeypatch):
    # Exercises the success path of ``get_account_scope`` directly: once a scheme is
    # plugged into ``_resolve_account_id``, this is the wiring that turns whatever id it
    # returns into the ``AccountScope`` route modules receive.
    monkeypatch.setattr(auth_module, "_resolve_account_id", lambda _inputs: "acct_resolved")

    app = FastAPI()

    @app.get("/whoami")
    async def whoami(account: AccountScopeDep) -> dict[str, str]:
        return {"account_id": account.account_id}

    response = TestClient(app).get("/whoami")

    assert response.status_code == 200
    assert response.json() == {"account_id": "acct_resolved"}


def test_dependency_override_is_the_test_only_way_to_inject_a_known_account():
    app = _build_app()
    app.dependency_overrides[get_account_scope] = lambda: AccountScope(account_id="acct_test_123")
    try:
        response = TestClient(app).get("/whoami")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"account_id": "acct_test_123"}


def test_override_cleared_reverts_to_the_fail_closed_production_path():
    # Proves the override is scoped to the app instance a test controls, not a global
    # switch: once cleared, the exact same app instance is unauthenticated again.
    app = _build_app()
    app.dependency_overrides[get_account_scope] = lambda: AccountScope(account_id="acct_test_123")
    TestClient(app).get("/whoami")
    app.dependency_overrides.clear()

    response = TestClient(app).get("/whoami")

    assert response.status_code == 401
