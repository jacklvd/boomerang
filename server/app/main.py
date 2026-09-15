"""FastAPI application entrypoint.

Wires the ASGI app and its cold-start lifespan. Route modules live under ``app.routes``
and are mounted through the single aggregator router there, so adding a route never
means editing this file.

Every ``/v1`` route module obtains its account scope from ``app.api.auth`` (depend on
``AccountScopeDep``) or, more usually, a repository already bound to that scope from
``app.api.deps`` (``ScopedRepositoryDep``), and raises errors from ``app.api.errors``
(``ApiError`` and its convenience constructors); this module wires the error envelope
onto the app so those errors reach the client in the contract's shape. ``/health`` stays
outside all of it: it does no I/O, requires no account, and touches no database.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import bedrock
from app.api.deps import database_lifespan
from app.api.errors import install_error_handling
from app.routes import api_router

# dev-note: app.config.Settings (the authentication configuration surface: credential and
# grant lifetimes, pairing, rate limits, CORS/origin policy) deliberately is NOT
# constructed here yet, even though app.config.settings_lifespan exists and is ready to be
# composed exactly like database_lifespan below. No route currently depends on it — see
# app/api/auth.py, which is still fully unimplemented — and this codebase's test suite has
# no fixture supplying values for it (unlike DATABASE_URL, which tests/conftest.py stubs
# for every test via an autouse fixture). Composing it into this lifespan unconditionally
# makes every test that drives this app through its real lifespan (see
# tests/test_main.py::test_health_reports_ok) fail with a pydantic ValidationError, since
# none of the ~20 required settings have -- or should have -- a default. Wire
# `settings_lifespan(app)` in here, the same way `database_lifespan(app)` is used below,
# in the same change that adds the first route depending on app.config.SettingsDep and
# a conftest.py fixture supplying it a value for tests.


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run cold-start work once per container, before the first request is served."""
    # dev-note: this runs on Lambda cold start, because the ASGI adapter is configured with
    # lifespan handling on. Anything cached for the warm lifetime of the container belongs
    # here — model config validation and the database engine now, SSM credential fetch when
    # USPS lands. If lifespan is ever turned off, none of it runs and the cache is silently
    # never populated.
    bedrock.verify_config()
    async with database_lifespan(app):
        yield


app = FastAPI(title="boomerang", lifespan=lifespan)
install_error_handling(app)
app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Deliberately does no I/O, so it stays honest about the process only."""
    return {"status": "ok"}
