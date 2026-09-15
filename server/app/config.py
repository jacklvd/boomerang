"""The application's configuration surface, and its fail-fast startup validation.

Every authentication-related number here has no default in code and no default in the
schema: an unset value must make the process refuse to start, not fall back to something
plausible. ``DATABASE_URL`` in :mod:`app.api.deps` and ``BEDROCK_MODEL`` in
:mod:`app.bedrock` already do this; this module extends the same posture to the
authentication surface (pairing, grants, refresh, dashboard sign-in, rate limits and
cross-origin policy) before any of that surface has route code of its own.

:class:`Settings` is built once per process from the environment and exposed two ways:

* :func:`get_settings` — a process-wide cached instance, for anything constructed once
  and reused (mirrors ``app.bedrock.client``'s ``lru_cache`` shape).
* ``SettingsDep`` — a FastAPI dependency for route handlers, reading back an instance
  installed on ``app.state`` by ``app.main``'s lifespan (mirrors
  ``app.api.deps.ScopedRepositoryDep`` and ``_require_session_factory``).

Three startup validators run as part of construction (see ``_check_*`` below) because
each one guards a property no reviewer can be trusted to remember on every future change:
the coarsening interval staying well under the idle limit, a dashboard credential's
lifetime equalling its grant's, and the dashboard/API origins sharing a registrable
domain so the ``SameSite=Lax`` dashboard cookie is not silently dead on arrival.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from pydantic import BeforeValidator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

# The attribute on ``app.state`` that ``settings_lifespan`` populates and
# ``_require_settings`` reads back. One name, written and read in this module only.
SETTINGS_STATE_ATTR = "settings"


def _seconds_to_timedelta(value: object) -> object:
    """Convert an integer (or numeric string) count of seconds into a ``timedelta``.

    Every duration in ``.env`` is written as a plain integer count of seconds — see
    ``server/.env.example`` — because that is what a deployer can set without consulting
    this module's source. Pydantic's own ``timedelta`` parsing only accepts ISO-8601
    duration strings (``PT3600S``) for text input, which is not that format, so each
    duration field runs its raw value through this converter first.
    """
    if isinstance(value, bool):
        # dev-note: bool is an int subclass, so pydantic's own timedelta parsing would
        # otherwise silently accept `True` as `timedelta(seconds=1)`. Raising here (rather
        # than returning the bool unchanged) is what actually makes that a validation
        # error instead of a silently-wrong duration.
        msg = "a duration must be an integer count of seconds, not a boolean"
        raise ValueError(msg)  # noqa: TRY004 - pydantic-core only wraps ValueError as a ValidationError
    if isinstance(value, int | float):
        return timedelta(seconds=value)
    if isinstance(value, str) and value.strip():
        try:
            return timedelta(seconds=int(value.strip()))
        except ValueError:
            return value
    return value


Seconds = Annotated[timedelta, BeforeValidator(_seconds_to_timedelta)]
"""A duration configured in the environment as a plain integer count of seconds."""


def _split_origins(value: object) -> object:
    """Accept a comma-separated string of origins, e.g. ``DASHBOARD_ORIGINS=a,b``.

    ``pydantic-settings`` parses a ``list[str]`` field from an env var as JSON by
    default, which makes a plain comma-separated ``.env`` entry invalid without this. A
    single origin with no comma is also accepted, as is a list passed in directly (e.g.
    from a test constructing ``Settings`` from a dict rather than the environment).
    """
    if isinstance(value, str):
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    return value


Origins = Annotated[list[str], NoDecode, BeforeValidator(_split_origins)]
"""A list of origins, read from the environment as a comma-separated string.

``NoDecode`` stops ``pydantic-settings`` from trying to JSON-decode the raw env value
before ``_split_origins`` runs — without it, a plain comma-separated string fails with a
JSON parse error before this module's own parsing gets a chance to run.
"""


# ---------------------------------------------------------------------------
# Registrable-domain check
#
# A dashboard session cookie set with SameSite=Lax survives a cross-site navigation but
# not a cross-site POST/fetch — the dashboard and the API must be same-site, i.e. share a
# registrable domain, or the cookie never reaches the API at all. Deciding "registrable
# domain" correctly requires the Public Suffix List: `example.vercel.app` and
# `other.vercel.app` do NOT share a registrable domain, because `vercel.app` is itself a
# public suffix, but a naive "last two labels" comparison would say they do.
#
# This codebase has no PSL dependency (adding one is out of scope for this ticket — see
# the report for this ticket), so the check below is deliberately incomplete:
#
# * It is exact for the ordinary case of a single-label public suffix (`.com`, `.io`,
#   `.dev`, `.app`, ...): "last two labels" is the correct registrable domain there.
# * It special-cases a short, hardcoded list of known multi-tenant hosting suffixes
#   (`vercel.app`, `netlify.app`, `github.io`, `pages.dev`, `herokuapp.com`, `fly.dev`,
#   `workers.dev`, `ngrok.io`, `ngrok-free.app`) so that subdomains of *those* are
#   correctly treated as NOT sharing a registrable domain with each other.
# * It does NOT know about multi-label ccTLD suffixes such as `co.uk` or `com.au`. Two
#   hosts ending in one of those would be wrongly reported as sharing a registrable
#   domain of e.g. `co.uk`. This is a real gap — see the report for this ticket.
#
# The failure mode is conservative in the direction that matters for this check's
# purpose: it is used to REJECT a configuration (refuse to start), never to silently
# permit one, so a wrong "they share a domain" verdict on a ccTLD is the dangerous
# direction and remains open. A wrong "they do NOT share a domain" verdict merely refuses
# to start a deployment that might actually have been fine, which is the safe side to
# err on for a fail-fast check.
_KNOWN_MULTI_TENANT_SUFFIXES = frozenset(
    {
        "vercel.app",
        "netlify.app",
        "github.io",
        "gitlab.io",
        "pages.dev",
        "herokuapp.com",
        "fly.dev",
        "workers.dev",
        "ngrok.io",
        "ngrok-free.app",
    }
)


def _hostname(origin: str) -> str:
    """Extract the lowercase hostname from an origin string such as ``https://a.b.com``."""
    return (urlsplit(origin).hostname or origin).lower()


def _registrable_domain(hostname: str) -> str:
    """Best-effort registrable domain: the last two dot-separated labels.

    See the module-level comment above this section for exactly what this does and does
    not get right. Never call this directly to decide "same site" — go through
    :func:`_shares_registrable_domain`, which also rejects known multi-tenant suffixes.
    """
    minimum_labels_for_a_registrable_domain = 2
    labels = hostname.split(".")
    if len(labels) >= minimum_labels_for_a_registrable_domain:
        return ".".join(labels[-2:])
    return hostname


def _shares_registrable_domain(host_a: str, host_b: str) -> bool:
    """Whether two hostnames share a registrable domain, as far as this module can tell."""
    if host_a == host_b:
        return True
    domain_a, domain_b = _registrable_domain(host_a), _registrable_domain(host_b)
    if domain_a != domain_b:
        return False
    return domain_a not in _KNOWN_MULTI_TENANT_SUFFIXES


class Settings(BaseSettings):
    """The application's fail-fast configuration surface.

    Constructed once per process — see ``app.main``'s lifespan — from environment
    variables (and, if present, a ``.env`` file; see ``server/.env.example`` for every
    variable this class reads and the unit each is in). Every field below is required:
    an unset variable raises during construction rather than at the moment something
    would have used a silently-wrong fallback.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # -- Credential and grant lifetimes -----------------------------------------------
    access_credential_lifetime: Seconds
    refresh_credential_lifetime: Seconds
    dashboard_access_credential_lifetime: Seconds

    grant_idle_limit: Seconds
    grant_absolute_limit: Seconds
    dashboard_grant_lifetime: Seconds

    # -- Pairing -------------------------------------------------------------------------
    pairing_lifetime: Seconds
    pairing_poll_interval: Seconds

    # -- Refresh rotation -----------------------------------------------------------------
    refresh_rotation_grace_window: Seconds

    # -- last_used_at coarsening ----------------------------------------------------------
    last_used_at_coarsening_interval: Seconds
    # dev-note: "far smaller" (the design docs' own wording) is not a checkable predicate,
    # and picking a ratio ourselves would be exactly the kind of invented authentication
    # number this configuration surface exists to forbid. The deployer states the ratio
    # explicitly; _check_coarsening_interval_is_far_smaller_than_idle_limit below only
    # enforces whatever ratio is configured. See this ticket's report: no design document
    # settles a number, so this field has no default either.
    coarsening_interval_to_idle_limit_ratio: float

    # -- Rate limits: each a ceiling and a window ------------------------------------------
    pairing_creation_rate_limit_count: int
    pairing_creation_rate_limit_window: Seconds
    pairing_redemption_rate_limit_count: int
    pairing_redemption_rate_limit_window: Seconds
    refresh_rate_limit_count: int
    refresh_rate_limit_window: Seconds

    # -- Origins and CORS -------------------------------------------------------------------
    # dev-note: exact, per-environment list — never a wildcard. The dashboard is a
    # same-site browser client (SameSite=Lax cookie); the extension is a cross-site
    # bearer-token client with no ambient credential. See
    # design/boomerang-extension-auth-proposal.md's "resulting posture" table.
    dashboard_origins: Origins
    extension_origin: str
    # dev-note: not in the brief's enumerated settings list, but required to run the
    # registrable-domain check below — the check needs to know what origin the API
    # itself is served from. Added here as its own explicit, named, no-default setting
    # rather than assumed or hardcoded. Flagged in this ticket's report.
    api_origin: str
    cors_preflight_max_age: Seconds

    @model_validator(mode="after")
    def _check_coarsening_interval_is_far_smaller_than_idle_limit(self) -> Settings:
        """Refuse to start if a stale ``last_used_at`` could outlive the idle limit.

        The idle limit is evaluated against ``last_used_at``, which is only refreshed
        every ``last_used_at_coarsening_interval``. If the interval is not comfortably
        smaller than the idle limit, a grant can go idle-expired in the database while
        still looking recently used, or vice versa. "Comfortably smaller" is configured
        explicitly as ``coarsening_interval_to_idle_limit_ratio`` rather than assumed.
        """
        interval = self.last_used_at_coarsening_interval
        idle_limit = self.grant_idle_limit
        ratio = self.coarsening_interval_to_idle_limit_ratio
        if ratio <= 1:
            msg = (
                "coarsening_interval_to_idle_limit_ratio must be greater than 1 "
                f"(configured: {ratio}); a ratio of 1 or less would let the idle limit "
                "be evaluated against a last_used_at value that is not meaningfully "
                "fresher than the limit itself."
            )
            raise ValueError(msg)
        if idle_limit < interval * ratio:
            msg = (
                "grant_idle_limit "
                f"({idle_limit}) is not at least coarsening_interval_to_idle_limit_ratio "
                f"({ratio}) times last_used_at_coarsening_interval ({interval}). "
                "last_used_at is only refreshed every coarsening interval, so an idle "
                "limit too close to that interval lets a grant be evaluated against a "
                "stale last_used_at value and outlive the limit it is supposed to enforce. "
                "Widen grant_idle_limit, shrink last_used_at_coarsening_interval, or "
                "lower the configured ratio if it was set unrealistically high."
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _check_dashboard_credential_lifetime_equals_grant_lifetime(self) -> Settings:
        """Refuse to start unless a dashboard access credential's lifetime equals its grant's.

        Per the API contract's 401 discriminator: a dashboard access credential is only
        ever valid for exactly as long as the dashboard grant that issued it, so its
        expiry can stand in for "grant revoked or expired" without a separate check. If
        the two lifetimes ever diverge, that shortcut silently stops being true.
        """
        access = self.dashboard_access_credential_lifetime
        grant = self.dashboard_grant_lifetime
        if access != grant:
            msg = (
                "dashboard_access_credential_lifetime "
                f"({access}) must equal dashboard_grant_lifetime ({grant}). A dashboard "
                "access credential's expiry is relied on to stand in for its grant's "
                "expiry (see the API contract's 401 discriminator); if the two lifetimes "
                "differ, a still-valid credential could outlive its grant, or a still-"
                "valid grant could be forced to re-authenticate early."
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _check_dashboard_and_api_origins_share_a_registrable_domain(self) -> Settings:
        """Refuse to start unless every dashboard origin is same-site with the API origin.

        The dashboard's session cookie is set with ``SameSite=Lax``, which is only sent
        on a cross-site request at all when the two origins share a registrable domain.
        See the module-level comment above ``_shares_registrable_domain`` for exactly
        what this check can and cannot verify without a Public Suffix List.
        """
        api_host = _hostname(self.api_origin)
        for dashboard_origin in self.dashboard_origins:
            dashboard_host = _hostname(dashboard_origin)
            if not _shares_registrable_domain(api_host, dashboard_host):
                msg = (
                    f"dashboard origin {dashboard_origin!r} does not appear to share a "
                    f"registrable domain with api_origin {self.api_origin!r}. The "
                    "dashboard session cookie is set with SameSite=Lax, which requires "
                    "the two to be same-site or the cookie will not be sent on a "
                    "cross-site request from the dashboard to the API. Note: this check "
                    "is a best-effort approximation, not a full Public Suffix List "
                    "lookup — see app/config.py for its known gaps."
                )
                raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide ``Settings`` instance, built once and reused.

    Mirrors ``app.bedrock.client``'s shape: one cached instance per warm container.
    Prefer the ``app.state``-backed dependency (``SettingsDep``) inside a request
    handler; use this directly only where a request is not available.
    """
    # dev-note: every field above has no default, by design (see the module docstring), so
    # mypy sees `Settings()` as a call missing ~20 required arguments. At runtime
    # pydantic-settings supplies them all from the environment (and `.env`) instead; that
    # behaviour is exactly what BaseSettings adds over a plain BaseModel, but mypy has no
    # visibility into it without the pydantic mypy plugin, which this project does not
    # enable (adding it is out of scope for this ticket — see its report).
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    """Drop the cached ``Settings`` instance, for tests that vary the environment."""
    get_settings.cache_clear()


@asynccontextmanager
async def settings_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the process-wide ``Settings`` instance for the lifetime of ``app``.

    Entered once from the FastAPI lifespan (see ``app.main``), exactly like
    ``app.api.deps.database_lifespan``. Building it here, rather than lazily on first
    request, is what makes a misconfigured deployment fail at cold start instead of on
    whichever request happens to touch it first.
    """
    setattr(app.state, SETTINGS_STATE_ATTR, get_settings())
    try:
        yield
    finally:
        setattr(app.state, SETTINGS_STATE_ATTR, None)


def _require_settings(app: FastAPI) -> Settings:
    """Read back the settings the lifespan installed, or fail loudly.

    Mirrors ``app.api.deps._require_session_factory``: nothing here builds a ``Settings``
    lazily, so reaching this with none installed means lifespan startup did not run.
    """
    settings = getattr(app.state, SETTINGS_STATE_ATTR, None)
    if settings is None:
        msg = (
            "Settings is missing: FastAPI lifespan startup did not run for this "
            "application. It is built once per process in app.main's lifespan and "
            "nothing builds one per request. Check that the ASGI adapter serving this "
            "app has lifespan handling enabled."
        )
        raise RuntimeError(msg)
    return settings  # type: ignore[no-any-return]


def get_settings_from_request(request: Request) -> Settings:
    """FastAPI dependency callable backing ``SettingsDep``."""
    return _require_settings(request.app)


SettingsDep = Annotated[Settings, Depends(get_settings_from_request)]
"""What route modules import: ``async def handler(settings: SettingsDep) -> ...``."""
