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
