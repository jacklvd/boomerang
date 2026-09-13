"""The account authentication seam.

Extension-to-server authentication is an undecided product question — see
``design/boomerang-extension-auth-proposal.md`` for the (unaccepted) proposal. This
module does not choose a scheme. It builds the one property every candidate scheme
agrees on: ``design/boomerang-api-contract.md`` section 3.2 requires that every ``/v1``
route resolve a server-side account id from a verified principal, and that "clients
never submit an ``account_id`` to choose the account being accessed."

Route modules depend on :data:`AccountScopeDep` (or call :func:`get_account_scope`
directly) to obtain a resolved :class:`AccountScope`. They never read an account id out
of a path, a query string, or a request body themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from app.api.errors import unauthenticated_error

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.datastructures import Headers


@dataclass(frozen=True, slots=True)
class AccountScope:
    """A resolved, server-side account identity for the current request.

    ``account_id`` is always a concrete ``str`` — never ``str | None``. There is no
    service-principal or "no account" variant: a route that has an ``AccountScope`` has
    a real account to scope its reads and writes to, full stop. Widening this to allow
    ``None`` would let a future caller quietly read across every account, because
    "unresolved" and "unrestricted" collapse to the same in-code representation the
    moment the type allows it.
    """

    account_id: str


@dataclass(frozen=True, slots=True)
class AuthenticationInputs:
    """The only request data the auth seam is allowed to see.

    Deliberately narrower than FastAPI's ``Request``: no path parameters, no query
    parameters, no body access. Whichever scheme is decided resolves an account id from
    headers and/or cookies only — that is the structural half of "never read from a
    body, path, or query parameter": the resolution function below is not merely asked
    not to read those, it is handed an object that cannot.
    """

    headers: Headers
    cookies: Mapping[str, str]


def _extract_authentication_inputs(request: Request) -> AuthenticationInputs:
    """Narrow an incoming ``Request`` down to only what the auth seam may read."""
    return AuthenticationInputs(headers=request.headers, cookies=request.cookies)


# =============================================================================================
# THE SEAM.
#
# Extension-to-server authentication is not yet decided (see the proposal cited in this
# module's docstring). Whichever scheme is chosen — cookie or bearer, Google exchange or
# extension keypair — plugs in by replacing the body of this function with real
# verification that returns a verified account id, or raises `unauthenticated_error()`.
#
# Until that decision lands, this function must keep failing closed:
#   - no default, test, or anonymous account;
#   - no environment variable or config flag that disables authentication;
#   - the only input it may consult is `inputs` (headers/cookies) — never path params,
#     query params, or the request body, which this function's signature cannot reach.
# =============================================================================================
def _resolve_account_id(inputs: AuthenticationInputs) -> str:  # noqa: ARG001 - seam signature
    """Resolve a verified account id from ``inputs``, or raise ``unauthenticated_error``.

    This is the single production seam for the decided authentication scheme. It is
    unconditional today: there is nothing here for a scheme to override, degrade, or
    bypass, so an unconfigured production deployment fails closed rather than serving an
    anonymous or default account.
    """
    raise unauthenticated_error(details={"cause": "authentication_not_configured"})


async def get_account_scope(request: Request) -> AccountScope:
    """FastAPI dependency yielding the resolved :class:`AccountScope` for this request.

    Route modules depend on this (directly, or through :data:`AccountScopeDep`) instead
    of reading identity off the request themselves. In tests, override it with FastAPI's
    own dependency-override mechanism — ``app.dependency_overrides[get_account_scope] =
    lambda: AccountScope(account_id="acct_known")`` — which only ever affects a
    ``FastAPI`` app instance a test holds a reference to; nothing in this module, or
    anywhere else in ``app/``, ever installs an override, so a running production
    process has no such switch to find.
    """
    inputs = _extract_authentication_inputs(request)
    account_id = _resolve_account_id(inputs)
    return AccountScope(account_id=account_id)


AccountScopeDep = Annotated[AccountScope, Depends(get_account_scope)]
"""Convenience alias for route modules: ``async def handler(account: AccountScopeDep) -> ...``."""
