"""Per-request data access for ``/v1`` route modules, and the startup wiring behind it.

A route module never builds a database session and never constructs a repository. It
depends on :data:`ScopedRepositoryDep` and receives a
:class:`~app.db.repository.ScopedRepository` already bound to the account the auth seam
resolved for this request::

    from app.api.deps import ScopedRepositoryDep

    @router.get("/thing")
    async def read_thing(repository: ScopedRepositoryDep) -> ThingResponse: ...

Two properties this module exists to make true by construction:

*Account scope comes from the principal only.* The account id handed to the repository
comes from :data:`~app.api.auth.AccountScopeDep` and from nowhere else. Route code is
never given an account id it could have read from a path, a query string, a body, or a
header, so the contract's "clients never submit an account id to choose the account
being accessed" is a shape of the dependency graph rather than a rule handlers must
remember.

*The engine is built once per process, not per request.* ``database_lifespan`` is
entered once from the FastAPI lifespan (see ``app.main``) and owns the engine and the
session factory for the warm lifetime of the container; each request borrows one session
from that factory and returns it. Nothing here builds an engine lazily, so a process that
was never configured fails at startup rather than on a user's first read.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

# dev-note: this module needs postponed annotations so the session-factory type below
# stays a type-only reference, which in turn makes ruff want every annotation-only
# import moved into the type-checking block. FastAPI resolves a dependency's parameter
# annotations at runtime, so moving this one would raise NameError on the first request.
# Route modules do not have this problem: they omit the postponed-annotations import and
# ruff leaves their dependency aliases alone (see app/routes/me.py).
from app.api.auth import AccountScopeDep  # noqa: TC001
from app.db.repository import ScopedRepository
from app.db.session import build_async_engine, build_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

    # dev-note: TID251 bans AsyncSession above app/db/ so that no code up here can hold a
    # session and run an unscoped query. This is a type-only reference used to spell the
    # session factory's generic parameter; the session object itself is never named, never
    # annotated, and never handed to anything but ScopedRepository's constructor.
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: TID251

DATABASE_URL_ENV = "DATABASE_URL"

# The attribute on ``app.state`` that ``database_lifespan`` populates and
# ``_require_session_factory`` reads back. One name, written and read in this module only.
SESSION_FACTORY_STATE_ATTR = "session_factory"


def _require_database_url() -> str:
    """Resolve the PostgreSQL URL from the environment, failing loudly if it is unset.

    There is deliberately no default and no fallback to a local or in-memory database.
    Every ``/v1`` route reads account data, so a process that silently pointed at an
    empty stand-in database would answer requests successfully with no orders, no
    policies and no preferences — a data-loss-shaped bug that looks like a working
    deployment. An unconfigured process must refuse to start instead.

    The driver prefix itself is validated by ``app.db.session.build_async_engine``.
    """
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        msg = (
            "DATABASE_URL is not set. There is deliberately no default: falling back to a "
            "local or in-memory database would let a misconfigured deployment answer every "
            "account read with an empty result instead of failing. Set it to the async "
            "psycopg DSN for this environment, e.g. "
            "postgresql+psycopg://user:password@host:5432/boomerang — the "
            "'postgresql+psycopg://' driver prefix is required and is checked at startup."
        )
        raise RuntimeError(msg)
    return database_url


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the process-wide engine and session factory for the lifetime of ``app``.

    Entered once from the FastAPI lifespan, which the ASGI-to-Lambda adapter runs on cold
    start. Building the engine here rather than per request is what makes connection
    pooling work at all; it is also what makes a missing or malformed ``DATABASE_URL`` a
    startup failure, which is the only place it can fail usefully.
    """
    engine = build_async_engine(_require_database_url())
    setattr(app.state, SESSION_FACTORY_STATE_ATTR, build_session_factory(engine))
    try:
        yield
    finally:
        setattr(app.state, SESSION_FACTORY_STATE_ATTR, None)
        await engine.dispose()


def _require_session_factory(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    """Read back the session factory the lifespan installed, or fail loudly.

    Nothing builds a factory lazily here on purpose. Reaching this with no factory means
    lifespan startup did not run — most often an ASGI adapter configured with lifespan
    handling turned off — and the honest answer is a loud server error, not a
    request-scoped engine that quietly works while connection pooling and the startup
    configuration check never happen.
    """
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        app.state, SESSION_FACTORY_STATE_ATTR, None
    )
    if factory is None:
        msg = (
            "The database session factory is missing: FastAPI lifespan startup did not "
            "run for this application. It is built once per process in app.main's "
            "lifespan and nothing builds one per request. Check that the ASGI adapter "
            "serving this app has lifespan handling enabled."
        )
        raise RuntimeError(msg)
    return factory


async def get_scoped_repository(
    request: Request,
    scope: AccountScopeDep,
) -> AsyncIterator[ScopedRepository]:
    """Yield a repository bound to this request's account, closing its session afterwards.

    The session lives exactly as long as the request: the ``async with`` closes it on the
    way out whether the handler returned or raised. ``scope`` is the only source of the
    account id — this function has no other account-shaped value available to pass.
    """
    session_factory = _require_session_factory(request.app)
    async with session_factory() as session:
        yield ScopedRepository(session, scope.account_id)


ScopedRepositoryDep = Annotated[ScopedRepository, Depends(get_scoped_repository)]
"""What route modules import: ``async def handler(repository: ScopedRepositoryDep) -> ...``."""
