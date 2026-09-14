"""The v1 error envelope: one closed shape for every non-success response.

``design/boomerang-api-contract.md`` section 4 defines this shape and its closed
``reason`` enum, and states that ``details`` must never carry raw upstream responses,
stack traces, or user data. Route modules never build a ``JSONResponse`` for an error
themselves: they raise :class:`ApiError` (or one of the convenience constructors below)
and :func:`install_error_handling` is the only place that turns any raised error —
ours, FastAPI's own validation errors, or a framework-level HTTP error — into the
contract's wire shape.

The ``reason`` enum is closed by contract: adding a member is a breaking change. Where a
status code needs to discriminate between causes that the contract does not give a
separate ``reason`` for (most importantly ``401 unauthenticated``), that discriminator
belongs in ``details``, never as a new enum value.
"""

from __future__ import annotations

import logging
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import FastAPI, Request
    from starlette.responses import Response

logger = logging.getLogger("app.api.errors")

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_STATE_KEY = "request_id"

# Any Starlette HTTPException at or above this status is a server-side failure, not a
# client mistake, when the contract's own reason table doesn't already cover the status.
_MIN_SERVER_ERROR_STATUS = 500

# Validation-error subtypes that mean "the body could not even be parsed as JSON", which
# the contract treats as 400 invalid_request rather than 422 validation_failed.
_JSON_DECODE_ERROR_TYPES = frozenset({"json_invalid", "json_type"})


class ErrorReason(StrEnum):
    """The v1 contract's closed error ``reason`` enum. Adding a member is a breaking change."""

    INVALID_REQUEST = "invalid_request"
    UNAUTHENTICATED = "unauthenticated"
    NOT_FOUND = "not_found"
    STATE_TRANSITION_NOT_ALLOWED = "state_transition_not_allowed"
    STATE_BLOCKED = "state_blocked"
    VALIDATION_FAILED = "validation_failed"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


# The contract's table 4 maps each reason to exactly one status. 409 is the only status
# shared by two reasons (state_transition_not_allowed, state_blocked); every `ApiError`
# names its own reason explicitly, so that ambiguity never needs to be resolved in reverse.
_STATUS_BY_REASON: dict[ErrorReason, int] = {
    ErrorReason.INVALID_REQUEST: status.HTTP_400_BAD_REQUEST,
    ErrorReason.UNAUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
    ErrorReason.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorReason.STATE_TRANSITION_NOT_ALLOWED: status.HTTP_409_CONFLICT,
    ErrorReason.STATE_BLOCKED: status.HTTP_409_CONFLICT,
    ErrorReason.VALIDATION_FAILED: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorReason.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorReason.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorReason.TEMPORARILY_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
}

# Reverse mapping used only for statuses that FastAPI/Starlette itself can raise without
# an explicit ErrorReason attached (an unmatched route, a method not allowed against a
# route that does exist, ...). 409 is deliberately absent — see the note above.
_REASON_BY_UNAMBIGUOUS_STATUS: dict[int, ErrorReason] = {
    status.HTTP_400_BAD_REQUEST: ErrorReason.INVALID_REQUEST,
    status.HTTP_401_UNAUTHORIZED: ErrorReason.UNAUTHENTICATED,
    status.HTTP_404_NOT_FOUND: ErrorReason.NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_CONTENT: ErrorReason.VALIDATION_FAILED,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorReason.RATE_LIMITED,
    status.HTTP_500_INTERNAL_SERVER_ERROR: ErrorReason.INTERNAL_ERROR,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorReason.TEMPORARILY_UNAVAILABLE,
}


class ErrorBody(BaseModel):
    """The exact wire shape from ``design/boomerang-api-contract.md`` section 4."""

    reason: ErrorReason
    message: str
    request_id: str
    details: dict[str, Any] | None = None


class ApiError(Exception):
    """Raise this (or a convenience constructor below) from route or service code.

    ``status_code`` is derived from ``reason`` through the contract's own table, so a
    caller can never accidentally pair a status and a reason the contract doesn't
    define.
    """

    def __init__(
        self,
        reason: ErrorReason,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Build an ``ApiError`` for ``reason``, deriving its HTTP status from the contract."""
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.details = details
        self.status_code = _STATUS_BY_REASON[reason]


def unauthenticated_error(*, details: dict[str, Any] | None = None) -> ApiError:
    """Build the ``401 unauthenticated`` error.

    ``reason`` is a closed enum, so a 401 subtype (no credential, expired, revoked,
    the auth scheme not yet configured, ...) must never become a new ``reason`` value.
    Pass the discriminator through ``details`` instead.
    """
    message = "Sign in to continue."
    return ApiError(ErrorReason.UNAUTHENTICATED, message, details=details)


def not_found_error() -> ApiError:
    """Build the ``404 not_found`` error.

    This is the single call site for both "no such resource" and "that resource
    belongs to another account" — the contract requires the two to be indistinguishable
    on the wire, and routing both cases through one function is what makes that true by
    construction rather than by convention.
    """
    message = "The requested resource was not found."
    return ApiError(ErrorReason.NOT_FOUND, message)


def _new_request_id() -> str:
    """Generate an opaque request correlator.

    Never a session id, never derived from any request input — it must not correlate
    two requests from the same install, only identify this one for a support report.
    """
    return f"req_{uuid.uuid4().hex}"


def get_request_id(request: Request) -> str:
    """Read the request id the request-id middleware attached to this request."""
    request_id = getattr(request.state, _REQUEST_ID_STATE_KEY, None)
    if request_id is None:  # pragma: no cover - defensive; the middleware below always sets this
        msg = "request_id was read before the request-id middleware ran"
        raise RuntimeError(msg)
    return str(request_id)


def _format_field_path(loc: tuple[int | str, ...]) -> str:
    """Render a pydantic error ``loc`` tuple as the contract's ``values[0]``-style path."""
    parts: list[str] = []
    for segment in loc:
        if isinstance(segment, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{segment}]"
            else:
                parts.append(f"[{segment}]")
        else:
            parts.append(str(segment))
    return ".".join(parts)


def _error_response(
    request: Request,
    reason: ErrorReason,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build the envelope JSON response shared by every exception handler below."""
    body = ErrorBody(
        reason=reason, message=message, request_id=get_request_id(request), details=details
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def install_error_handling(app: FastAPI) -> None:
    """Wire the request-id middleware and every exception handler onto ``app``.

    This is the only place in the codebase that constructs the wire-level error
    response. Route modules raise :class:`ApiError`; FastAPI raises
    ``RequestValidationError`` for a malformed body or an unknown/invalid field;
    Starlette raises its own ``HTTPException`` for things like an unmatched route.
    All three, plus any otherwise-unhandled exception, are normalized here.
    """

    @app.middleware("http")
    async def _assign_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach an opaque, per-request id to ``request.state`` and echo it as a header."""
        request_id = _new_request_id()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        """Turn a raised ``ApiError`` into its wire envelope."""
        return _error_response(request, exc.reason, exc.message, exc.status_code, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Distinguish malformed JSON (400) from a typed field violation (422)."""
        errors = exc.errors()
        if any(error["type"] in _JSON_DECODE_ERROR_TYPES for error in errors):
            message = "The request body is not valid JSON."
            return _error_response(
                request, ErrorReason.INVALID_REQUEST, message, status.HTTP_400_BAD_REQUEST
            )

        fields = [
            {"path": _format_field_path(error["loc"][1:]), "message": error["msg"]}
            for error in errors
        ]
        message = "One or more fields are invalid."
        return _error_response(
            request,
            ErrorReason.VALIDATION_FAILED,
            message,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Normalize a framework-raised HTTP error (an unmatched route, a bad method, ...)."""
        reason = _REASON_BY_UNAMBIGUOUS_STATUS.get(exc.status_code)
        if reason is None:
            reason = (
                ErrorReason.INTERNAL_ERROR
                if exc.status_code >= _MIN_SERVER_ERROR_STATUS
                else ErrorReason.INVALID_REQUEST
            )
        message = (
            exc.detail
            if isinstance(exc.detail, str) and exc.detail
            else "The request could not be completed."
        )
        return _error_response(request, reason, message, exc.status_code)

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Catch anything else so a crash never leaks a stack trace to the client."""
        logger.error("unhandled_error", exc_info=exc, extra={"request_id": get_request_id(request)})
        message = "Something went wrong. Try again."
        return _error_response(
            request, ErrorReason.INTERNAL_ERROR, message, status.HTTP_500_INTERNAL_SERVER_ERROR
        )
