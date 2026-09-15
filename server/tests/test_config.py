"""Tests for the authentication configuration surface and its fail-fast validation.

``app.config.Settings`` is not yet wired into ``app.main``'s production lifespan (see the
dev-note there): no route depends on it yet, and this codebase's test fixtures do not
supply values for it the way ``tests/conftest.py``'s ``stub_database_url`` does for
``DATABASE_URL``. So every test here builds its own throwaway app (mirroring
``tests/conftest.py``'s ``api_app`` fixture) rather than driving ``app.main.app``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import config

# Every required field, with values that satisfy all three cross-field validators:
# * coarsening_interval_to_idle_limit_ratio (10) times the coarsening interval (3600s)
#   is comfortably under grant_idle_limit (2_592_000s).
# * dashboard_access_credential_lifetime equals dashboard_grant_lifetime (3600s).
# * every dashboard origin shares a registrable domain with api_origin (example.com).
COMPLETE_ENV = {
    "ACCESS_CREDENTIAL_LIFETIME": "900",
    "REFRESH_CREDENTIAL_LIFETIME": "2592000",
    "DASHBOARD_ACCESS_CREDENTIAL_LIFETIME": "3600",
    "GRANT_IDLE_LIMIT": "2592000",
    "GRANT_ABSOLUTE_LIMIT": "31536000",
    "DASHBOARD_GRANT_LIFETIME": "3600",
    "PAIRING_LIFETIME": "600",
    "PAIRING_POLL_INTERVAL": "2",
    "REFRESH_ROTATION_GRACE_WINDOW": "30",
    "LAST_USED_AT_COARSENING_INTERVAL": "3600",
    "COARSENING_INTERVAL_TO_IDLE_LIMIT_RATIO": "10",
    "PAIRING_CREATION_RATE_LIMIT_COUNT": "5",
    "PAIRING_CREATION_RATE_LIMIT_WINDOW": "60",
    "PAIRING_REDEMPTION_RATE_LIMIT_COUNT": "10",
    "PAIRING_REDEMPTION_RATE_LIMIT_WINDOW": "60",
    "REFRESH_RATE_LIMIT_COUNT": "20",
    "REFRESH_RATE_LIMIT_WINDOW": "60",
    "DASHBOARD_ORIGINS": "https://dashboard.example.com",
    "EXTENSION_ORIGIN": "chrome-extension://abcdefghijklmnop",
    "API_ORIGIN": "https://api.example.com",
    "CORS_PREFLIGHT_MAX_AGE": "600",
}


@pytest.fixture
def complete_env(monkeypatch):
    """Set every required variable to a mutually-consistent, valid value."""
    for key, value in COMPLETE_ENV.items():
        monkeypatch.setenv(key, value)
    config.clear_settings_cache()
    yield
    config.clear_settings_cache()


def _construct() -> config.Settings:
    """Construct ``Settings`` from the current environment.

    Every field is required with no default (see ``app/config.py``'s module docstring),
    so mypy sees a bare ``Settings()`` call as missing ~20 required constructor arguments —
    it has no visibility into pydantic-settings supplying them all from the environment at
    runtime (this project does not enable the pydantic mypy plugin; see this ticket's
    report). Routing every construction in this file through one ignored call keeps that
    limitation in one place instead of scattered across every test.
    """
    return config.Settings()  # type: ignore[call-arg]


def _construct_ignoring_any_env_file() -> config.Settings:
    """Like :func:`_construct`, but for a test that must not pick up a stray ``.env`` file."""
    return config.Settings(_env_file=None)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Baseline: a fully configured environment constructs cleanly
# ---------------------------------------------------------------------------


def test_a_fully_configured_environment_constructs(complete_env):
    settings = _construct()

    assert settings.access_credential_lifetime == timedelta(seconds=900)
    assert settings.dashboard_origins == ["https://dashboard.example.com"]
    assert settings.extension_origin == "chrome-extension://abcdefghijklmnop"
    assert settings.api_origin == "https://api.example.com"
    assert settings.pairing_creation_rate_limit_count == 5


def test_a_required_variable_with_no_value_anywhere_fails_loudly(monkeypatch):
    for key in COMPLETE_ENV:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValidationError, match="access_credential_lifetime"):
        _construct_ignoring_any_env_file()


# ---------------------------------------------------------------------------
# Seconds: an integer count of seconds, not an ISO-8601 duration string
# ---------------------------------------------------------------------------


def test_a_duration_is_read_as_a_plain_integer_count_of_seconds(complete_env, monkeypatch):
    monkeypatch.setenv("PAIRING_LIFETIME", "120")
    settings = _construct()
    assert settings.pairing_lifetime == timedelta(seconds=120)


def test_a_duration_field_also_accepts_an_int_passed_in_directly(complete_env):
    # Exercises the same BeforeValidator when Settings is constructed programmatically
    # (e.g. by a future test double) rather than from the environment.
    settings = config.Settings.model_validate({**_construct().model_dump(), "pairing_lifetime": 42})
    assert settings.pairing_lifetime == timedelta(seconds=42)


def test_a_non_numeric_duration_string_fails_validation(complete_env, monkeypatch):
    monkeypatch.setenv("PAIRING_LIFETIME", "soon")
    with pytest.raises(ValidationError, match="pairing_lifetime"):
        _construct()


def test_an_empty_duration_string_fails_validation(complete_env, monkeypatch):
    monkeypatch.setenv("PAIRING_LIFETIME", "   ")
    with pytest.raises(ValidationError, match="pairing_lifetime"):
        _construct()


def test_a_boolean_is_not_silently_accepted_as_a_duration(complete_env):
    # bool is an int subclass in Python; without an explicit guard `True` would silently
    # become a one-second timedelta instead of failing validation.
    with pytest.raises(ValidationError, match="pairing_lifetime"):
        config.Settings.model_validate({**_construct().model_dump(), "pairing_lifetime": True})


def test_none_is_not_a_valid_duration(complete_env):
    with pytest.raises(ValidationError, match="pairing_lifetime"):
        config.Settings.model_validate({**_construct().model_dump(), "pairing_lifetime": None})


# ---------------------------------------------------------------------------
# Origins: a comma-separated list, not JSON
# ---------------------------------------------------------------------------


def test_dashboard_origins_accepts_a_comma_separated_list(complete_env, monkeypatch):
    monkeypatch.setenv(
        "DASHBOARD_ORIGINS", "https://dashboard.example.com, https://staging.example.com"
    )
    settings = _construct()
    assert settings.dashboard_origins == [
        "https://dashboard.example.com",
        "https://staging.example.com",
    ]


def test_dashboard_origins_accepts_a_list_passed_in_directly(complete_env):
    settings = config.Settings.model_validate(
        {**_construct().model_dump(), "dashboard_origins": ["https://dashboard.example.com"]}
    )
    assert settings.dashboard_origins == ["https://dashboard.example.com"]


# ---------------------------------------------------------------------------
# Validator: coarsening interval must be far smaller than the grant idle limit
# ---------------------------------------------------------------------------


def test_a_ratio_of_one_or_less_is_rejected(complete_env, monkeypatch):
    monkeypatch.setenv("COARSENING_INTERVAL_TO_IDLE_LIMIT_RATIO", "1")
    with pytest.raises(ValidationError, match="must be greater than 1"):
        _construct()


def test_an_idle_limit_too_close_to_the_coarsening_interval_is_rejected(complete_env, monkeypatch):
    # The interval (3600s) times the configured ratio (10) is 36000s, well above this.
    monkeypatch.setenv("GRANT_IDLE_LIMIT", "3600")
    with pytest.raises(
        ValidationError, match="not at least coarsening_interval_to_idle_limit_ratio"
    ):
        _construct()


def test_an_idle_limit_comfortably_above_the_ratio_passes(complete_env, monkeypatch):
    monkeypatch.setenv("GRANT_IDLE_LIMIT", "36000")  # exactly interval * ratio
    settings = _construct()
    assert settings.grant_idle_limit == timedelta(seconds=36000)


# ---------------------------------------------------------------------------
# Validator: dashboard access credential lifetime must equal grant lifetime
# ---------------------------------------------------------------------------


def test_a_mismatched_dashboard_credential_and_grant_lifetime_is_rejected(
    complete_env, monkeypatch
):
    monkeypatch.setenv("DASHBOARD_ACCESS_CREDENTIAL_LIFETIME", "1800")
    with pytest.raises(ValidationError, match="must equal dashboard_grant_lifetime"):
        _construct()


def test_a_matching_dashboard_credential_and_grant_lifetime_passes(complete_env):
    settings = _construct()
    assert settings.dashboard_access_credential_lifetime == settings.dashboard_grant_lifetime


# ---------------------------------------------------------------------------
# Validator: dashboard and API origins must share a registrable domain
# ---------------------------------------------------------------------------


def test_an_unrelated_domain_is_rejected(complete_env, monkeypatch):
    monkeypatch.setenv("API_ORIGIN", "https://api.example.com")
    monkeypatch.setenv("DASHBOARD_ORIGINS", "https://dashboard.otherdomain.com")
    with pytest.raises(ValidationError, match="does not appear to share a registrable domain"):
        _construct()


def test_a_shared_multi_tenant_hosting_suffix_is_rejected(complete_env, monkeypatch):
    # example.vercel.app and other.vercel.app do NOT share a registrable domain: vercel.app
    # is itself a public suffix. A naive "last two labels" comparison would wrongly accept
    # this, which is exactly the failure mode this check exists to catch.
    monkeypatch.setenv("API_ORIGIN", "https://other.vercel.app")
    monkeypatch.setenv("DASHBOARD_ORIGINS", "https://example.vercel.app")
    with pytest.raises(ValidationError, match="does not appear to share a registrable domain"):
        _construct()


def test_an_identical_origin_trivially_shares_a_registrable_domain(complete_env, monkeypatch):
    monkeypatch.setenv("API_ORIGIN", "https://app.example.com")
    monkeypatch.setenv("DASHBOARD_ORIGINS", "https://app.example.com")
    settings = _construct()
    assert settings.dashboard_origins == ["https://app.example.com"]


def test_ordinary_subdomains_of_the_same_domain_share_a_registrable_domain(
    complete_env, monkeypatch
):
    monkeypatch.setenv("API_ORIGIN", "https://api.example.com")
    monkeypatch.setenv("DASHBOARD_ORIGINS", "https://dashboard.example.com")
    settings = _construct()
    assert settings.api_origin == "https://api.example.com"


def test_every_dashboard_origin_is_checked_not_just_the_first(complete_env, monkeypatch):
    # The first origin here is fine; the second is not. Both must be checked, so this
    # must fail even though a check that stopped after the first origin would pass it.
    monkeypatch.setenv("API_ORIGIN", "https://api.example.com")
    monkeypatch.setenv(
        "DASHBOARD_ORIGINS", "https://dashboard.example.com,https://dashboard.unrelated.org"
    )
    with pytest.raises(ValidationError, match=r"dashboard\.unrelated\.org"):
        _construct()


def test_a_hostname_with_no_dots_is_handled_without_crashing(complete_env, monkeypatch):
    # A bare single-label host (typical only in local dev) has no "last two labels" to
    # take; the registrable-domain approximation must fall back to the whole hostname
    # rather than raising an IndexError, and two different single-label hosts must still
    # be correctly reported as not sharing a registrable domain.
    monkeypatch.setenv("API_ORIGIN", "http://apihost:8000")
    monkeypatch.setenv("DASHBOARD_ORIGINS", "http://dashboardhost:3000")
    with pytest.raises(ValidationError, match="does not appear to share a registrable domain"):
        _construct()


def test_identical_single_label_hostnames_trivially_share_a_domain(complete_env, monkeypatch):
    monkeypatch.setenv("API_ORIGIN", "http://localhost:8000")
    monkeypatch.setenv("DASHBOARD_ORIGINS", "http://localhost:3000")
    settings = _construct()
    assert settings.api_origin == "http://localhost:8000"


# ---------------------------------------------------------------------------
# get_settings(): one cached instance per process, like app.bedrock.client()
# ---------------------------------------------------------------------------


def test_get_settings_is_cached(complete_env):
    assert config.get_settings() is config.get_settings()


def test_clear_settings_cache_forces_a_fresh_instance(complete_env, monkeypatch):
    first = config.get_settings()
    monkeypatch.setenv("PAIRING_LIFETIME", "999")
    config.clear_settings_cache()
    second = config.get_settings()

    assert first is not second
    assert second.pairing_lifetime == timedelta(seconds=999)


# ---------------------------------------------------------------------------
# The app.state / dependency wiring, mirroring app.api.deps's session-factory pattern
# ---------------------------------------------------------------------------


def _settings_probe_app() -> FastAPI:
    """A throwaway app installing ``settings_lifespan`` and one route depending on it.

    Mirrors ``tests/conftest.py``'s ``api_app`` fixture, but for ``app.config`` rather
    than the real ``/v1`` router: nothing in ``app.main`` wires this lifespan in yet (see
    the dev-note there), so there is no production app to drive this dependency through.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with config.settings_lifespan(app):
            yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/probe")
    def probe(settings: config.SettingsDep) -> dict[str, float]:
        return {"pairing_lifetime_seconds": settings.pairing_lifetime.total_seconds()}

    return app


def test_settings_is_installed_on_app_state_once_per_process(complete_env):
    app = _settings_probe_app()

    with TestClient(app):
        during_startup = app.state.settings
        assert during_startup is not None
        assert app.state.settings is during_startup

    assert app.state.settings is None


def test_the_dependency_resolves_the_settings_the_lifespan_installed(complete_env):
    app = _settings_probe_app()

    with TestClient(app) as client:
        response = client.get("/probe")

    assert response.status_code == 200
    assert response.json() == {"pairing_lifetime_seconds": 600.0}


def test_a_request_without_lifespan_startup_fails_loudly_rather_than_silently(complete_env):
    # No settings on app.state means lifespan startup never ran - mirrors
    # app.api.deps's equivalent test for the database session factory.
    app = _settings_probe_app()

    response = TestClient(app, raise_server_exceptions=False).get("/probe")

    assert response.status_code == 500


def test_require_settings_names_the_missing_lifespan_directly():
    app = FastAPI()

    with pytest.raises(RuntimeError, match="Settings is missing"):
        config._require_settings(app)  # noqa: SLF001 - the failure mode is the point
