"""The one UI-ready dashboard snapshot: account-wide metrics plus a filtered candidate page.

``GET /v1/dashboard`` and ``GET /v1/items/{item_id}`` share the same candidate shape and
the same urgency/next-action derivation, both of which live in ``app.routes._candidates``
so the two routes cannot drift apart. This module owns only what is specific to the
dashboard: the query parameters, the account-wide metrics, the urgency legend, and the
in-memory sort/filter/paginate pass described below.

``ScopedRepository.list_order_items()`` is the one read this route makes. Metrics are
account-wide by contract regardless of any filter a caller supplies, which means every
item has to be loaded and considered no matter what the caller asked for - there is no
filtered query that would let a database-side ``LIMIT`` reduce the read. Sorting,
filtering and pagination are therefore all done here, in memory, over that one
unfiltered read, rather than by adding a second, paginated repository method that would
not actually reduce the amount of data fetched.
"""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Final, cast

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import ScopedRepositoryDep
from app.api.errors import ApiError, ErrorReason
from app.db.models import OrderItemRow, OrderRow, ReturnPolicyRow, ReturnSummaryRow
from app.models import Money, PolicyEligibility, PolicyRule, ReturnState, UrgencyLevel
from app.routes._candidates import (
    CRITICAL_MAX_DAYS,
    SOON_MAX_DAYS,
    DatesView,
    ItemView,
    PolicyView,
    ReturnCandidate,
    ReturnSummaryView,
    Urgency,
    derive_urgency,
    fee,
    money,
    next_action,
    retailer_ref,
    return_by,
)

router = APIRouter(tags=["dashboard"])

# The reverse of base64.urlsafe_b64encode's own alphabet substitution, applied before
# decoding so a client-supplied cursor can use the URL-safe alphabet while this module
# reuses the standard-alphabet decoder underneath.
_URLSAFE_TO_STANDARD: Final = str.maketrans("-_", "+/")


class SortOption(StrEnum):
    """The dashboard's closed sort vocabulary. Only one member exists in v1."""

    CLOSING_SOONEST = "closing_soonest"


class DashboardMetrics(BaseModel):
    """Account-wide headline figures, unaffected by any ``candidates`` filter."""

    as_of: datetime
    closing_soon_max_days: int
    closing_soon_count: int
    in_progress_count: int
    carrier_handoff_count: int
    returnable_value_by_currency: list[Money]


class UrgencyLegendEntry(BaseModel):
    """One row of the legend the dashboard uses to explain its urgency thresholds."""

    level: UrgencyLevel
    label: str
    min_days: int | None
    max_days: int | None


class Page(BaseModel):
    """Pagination state for the candidate list."""

    next_cursor: str | None


class DashboardQuery(BaseModel):
    """The dashboard's query parameters, bundled into one model.

    FastAPI treats every field of a model annotated with ``Query()`` as its own query
    parameter with its own name in the OpenAPI schema - bundling them here is purely so
    the route function itself takes one parameter instead of five, it changes nothing
    about how a client calls the endpoint.
    """

    sort: SortOption = SortOption.CLOSING_SOONEST
    state: list[ReturnState] = Field(default_factory=list)
    urgency: list[UrgencyLevel] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = None


class DashboardResponse(BaseModel):
    """The complete dashboard payload: exactly these four top-level concerns.

    There is deliberately no top-level ``generated_at`` here, unlike the item-detail
    response - every candidate's urgency is derived as of ``metrics.as_of`` instead, so
    that figure is the single snapshot instant for the whole response rather than one
    more field routes would have to keep in sync.
    """

    metrics: DashboardMetrics
    urgency_legend: list[UrgencyLegendEntry]
    candidates: list[ReturnCandidate]
    page: Page


@dataclass(frozen=True, slots=True)
class _Row:
    """One account item enriched with everything the sort, filter and metrics passes need.

    Computed once per request rather than recomputed at every use site.
    """

    item: OrderItemRow
    order: OrderRow
    policy: ReturnPolicyRow
    summary: ReturnSummaryRow
    return_by_value: date | None
    urgency: Urgency


@dataclass(frozen=True, slots=True)
class _CursorKey:
    """The sort key carried by an opaque pagination cursor."""

    return_by: date | None
    retailer_name: str
    item_id: str


def _urgency_legend() -> list[UrgencyLegendEntry]:
    """Build the fixed legend describing the server's current urgency thresholds.

    The labels are normative wire values, not display copy this module is free to
    reword - they, and the day boundaries, must match the contract's worked example
    exactly so the UI renders the same thresholds the server actually used.
    """
    return [
        UrgencyLegendEntry(
            level=UrgencyLevel.EXPIRED, label="Deadline passed", min_days=None, max_days=-1
        ),
        UrgencyLegendEntry(
            level=UrgencyLevel.CRITICAL, label="Act now", min_days=0, max_days=CRITICAL_MAX_DAYS
        ),
        UrgencyLegendEntry(
            level=UrgencyLevel.SOON,
            label="Closing soon",
            min_days=CRITICAL_MAX_DAYS + 1,
            max_days=SOON_MAX_DAYS,
        ),
        UrgencyLegendEntry(
            level=UrgencyLevel.LATER,
            label="More time",
            min_days=SOON_MAX_DAYS + 1,
            max_days=None,
        ),
        UrgencyLegendEntry(
            level=UrgencyLevel.UNKNOWN, label="Deadline unknown", min_days=None, max_days=None
        ),
    ]


def _build_rows(items: list[OrderItemRow], as_of: datetime) -> list[_Row]:
    """Enrich every account item with its urgency, skipping incomplete rows.

    An item with no stored policy or no stored return summary is left out of both the
    candidate list and every metric below, rather than failing the whole response.
    Ingestion normally creates a policy and a summary together with the item itself, so
    a gap here means some other row's invariant broke - but this is a list endpoint, and
    the correct failure mode for one bad row is to omit that row, not to deny the user
    their entire dashboard the way the single-item read is allowed to 404.
    """
    rows: list[_Row] = []
    for item in items:
        policy = item.return_policy
        summary = item.return_summary
        if policy is None or summary is None:
            continue
        return_by_fact = return_by(policy)
        return_by_value = return_by_fact.value if return_by_fact is not None else None
        rows.append(
            _Row(
                item=item,
                order=item.order,
                policy=policy,
                summary=summary,
                return_by_value=return_by_value,
                urgency=derive_urgency(return_by_value, as_of),
            )
        )
    return rows


def _sort_key(row: _Row) -> tuple[bool, date, str, str]:
    """Order rows the way ``closing_soonest`` sorts them.

    Known deadlines ascending (expired dates included), unknown deadlines last, ties
    broken by retailer name and then item id.

    The leading ``bool`` is what pushes every unknown-deadline row after every
    known-deadline one: ``False < True``, so it is never compared against the date
    field across that boundary. The placeholder date used for unknown rows is only ever
    compared against other unknown rows, where it is identical for all of them and the
    ordering falls through to retailer name and item id exactly as it does for a tie
    between two known dates.
    """
    unknown = row.return_by_value is None
    date_component = row.return_by_value if row.return_by_value is not None else date.max
    return (unknown, date_component, row.order.retailer_name, row.item.id)


def _cursor_sort_key(key: _CursorKey) -> tuple[bool, date, str, str]:
    """Project a decoded cursor into the same tuple shape ``_sort_key`` produces.

    That lets a page boundary be found with a plain tuple comparison.
    """
    unknown = key.return_by is None
    date_component = key.return_by if key.return_by is not None else date.max
    return (unknown, date_component, key.retailer_name, key.item_id)


def _encode_cursor(key: _CursorKey) -> str:
    """Encode a page boundary as an opaque, unpadded base64url string.

    dev-note: this encoding is private to this route and opaque to every client - it is
    never documented as a wire format and may change shape at any time. It exists only
    so ``read_dashboard`` can find where the previous page left off; nothing outside
    this module should ever construct or parse one.
    """
    payload = {
        "return_by": key.return_by.isoformat() if key.return_by is not None else None,
        "retailer_name": key.retailer_name,
        "item_id": key.item_id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _parse_cursor_key(cursor: str) -> _CursorKey:
    """Decode ``cursor`` into a :class:`_CursorKey`, raising a builtin error on any malformed input.

    Kept separate from :func:`_decode_cursor` so the validation failures it raises are
    never themselves raised from inside a ``try`` block.
    """
    padded = cursor + "=" * (-len(cursor) % 4)
    raw = base64.b64decode(padded.translate(_URLSAFE_TO_STANDARD), validate=True)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        msg = "cursor payload must be a JSON object"
        raise TypeError(msg)
    return_by_raw = payload["return_by"]
    retailer_name = payload["retailer_name"]
    item_id = payload["item_id"]
    if return_by_raw is not None and not isinstance(return_by_raw, str):
        msg = "cursor return_by must be a string or null"
        raise TypeError(msg)
    if not isinstance(retailer_name, str) or not isinstance(item_id, str):
        msg = "cursor retailer_name and item_id must be strings"
        raise TypeError(msg)
    return_by_value = date.fromisoformat(return_by_raw) if return_by_raw is not None else None
    return _CursorKey(return_by=return_by_value, retailer_name=retailer_name, item_id=item_id)


def _cursor_validation_error() -> ApiError:
    """Build the ``422`` raised for a cursor that fails to decode.

    A malformed or truncated cursor is a client validation failure, the same status an
    unrecognized filter value gets - never a ``500``, and never a silent reset back to
    page one, which would hide a real client-side bug behind a confusing empty diff.
    """
    message = "The cursor is malformed or has expired. Request the first page without one."
    return ApiError(ErrorReason.VALIDATION_FAILED, message, details={"field": "cursor"})


def _decode_cursor(cursor: str) -> _CursorKey:
    """Decode an opaque pagination cursor, turning any decode failure into a ``422``."""
    try:
        return _parse_cursor_key(cursor)
    except (binascii.Error, ValueError, TypeError, KeyError) as exc:
        raise _cursor_validation_error() from exc


def _closing_soon(row: _Row) -> bool:
    """Apply the data model's exact ``closing_soon_count`` predicate to one row."""
    days_remaining = row.urgency.days_remaining
    return (
        days_remaining is not None
        and 0 <= days_remaining <= SOON_MAX_DAYS
        and row.policy.eligibility is not PolicyEligibility.INELIGIBLE
        and row.summary.state not in (ReturnState.HANDED_TO_CARRIER, ReturnState.COMPLETE)
    )


def _counts_toward_returnable_value(row: _Row) -> bool:
    """Decide whether one row's price contributes to ``returnable_value_by_currency``.

    A known price is required - an unknown price is excluded rather than treated as
    zero, so the headline figure never understates itself by averaging in a guess.
    """
    return (
        row.summary.state not in (ReturnState.HANDED_TO_CARRIER, ReturnState.COMPLETE)
        and row.policy.eligibility is not PolicyEligibility.INELIGIBLE
        and row.urgency.level is not UrgencyLevel.EXPIRED
        and row.item.price_amount_minor is not None
        and row.item.price_currency is not None
    )


def _compute_metrics(rows: list[_Row], as_of: datetime) -> DashboardMetrics:
    """Compute every account-wide figure over the full, unfiltered row set.

    Called once per request against every row this account owns, before any ``state``
    or ``urgency`` filter is applied - the contract's central rule for this route is
    that a filter narrows ``candidates`` and never changes a headline number.
    """
    closing_soon_count = 0
    in_progress_count = 0
    carrier_handoff_count = 0
    totals_by_currency: dict[str, int] = {}
    for row in rows:
        if row.summary.state is ReturnState.IN_PROGRESS:
            in_progress_count += 1
        if row.summary.state is ReturnState.HANDED_TO_CARRIER:
            carrier_handoff_count += 1
        if _closing_soon(row):
            closing_soon_count += 1
        if _counts_toward_returnable_value(row):
            # dev-note: _counts_toward_returnable_value already required both columns to
            # be non-null, so the cast documents that instead of re-branching on it.
            currency = cast("str", row.item.price_currency)
            amount = cast("int", row.item.price_amount_minor)
            totals_by_currency[currency] = totals_by_currency.get(currency, 0) + amount

    return DashboardMetrics(
        as_of=as_of,
        closing_soon_max_days=SOON_MAX_DAYS,
        closing_soon_count=closing_soon_count,
        in_progress_count=in_progress_count,
        carrier_handoff_count=carrier_handoff_count,
        # dev-note: sorted by currency code so the array is deterministic across
        # requests rather than following whatever order the rows happened to arrive in.
        returnable_value_by_currency=[
            Money(amount_minor=amount, currency=currency)
            for currency, amount in sorted(totals_by_currency.items())
        ],
    )


def _to_candidate(row: _Row) -> ReturnCandidate:
    """Project one enriched row into the wire-shared ``ReturnCandidate`` model."""
    return ReturnCandidate(
        item_id=row.item.id,
        order_id=row.item.order_id,
        retailer=retailer_ref(row.order),
        order_reference=row.order.retailer_order_reference,
        item=ItemView(
            description=row.item.description,
            variant=row.item.variant,
            quantity=row.item.quantity,
            price=money(row.item.price_amount_minor, row.item.price_currency),
        ),
        dates=DatesView(
            ordered_on=row.order.ordered_on,
            delivered_on=row.item.delivered_on,
            return_by=return_by(row.policy),
        ),
        policy=PolicyView(
            eligibility=row.policy.eligibility,
            fee=fee(row.policy),
            rules=[
                PolicyRule(
                    id=rule.id, text=rule.text, origin=rule.origin, confidence=rule.confidence
                )
                for rule in row.policy.rules
            ],
        ),
        urgency=row.urgency,
        return_summary=ReturnSummaryView(
            state=row.summary.state,
            update_source=row.summary.update_source,
            handoff_evidence=row.summary.handoff_evidence,
            observed_at=row.summary.observed_at,
            updated_at=row.summary.updated_at,
        ),
        next_action=next_action(row.summary.state, row.policy.eligibility, row.urgency.level),
    )


@router.get("/dashboard")
async def read_dashboard(
    repository: ScopedRepositoryDep,
    query: Annotated[DashboardQuery, Query()],
) -> DashboardResponse:
    """Return the signed-in account's dashboard snapshot.

    ``metrics`` is computed over every item this account owns, regardless of ``state``
    or ``urgency``; only ``candidates`` and pagination are narrowed by those filters.
    ``sort``, ``state`` and ``urgency`` are typed as closed enums (or lists of them), so
    FastAPI's own request validation turns an unrecognized value into a ``422`` before
    this function ever runs - there is no branch here that re-checks them. ``state`` and
    ``urgency`` default to an empty list, which reads as "no filter" (every value
    matches) rather than "match nothing" - an empty list is what a client that supplied
    no repeated query parameter at all receives from FastAPI.
    """
    # dev-note: the only sort order this route currently defines is the default itself;
    # ``query.sort`` still has to be a real, validated field so an unrecognized value
    # 422s rather than being silently accepted, even though no branch below reads it.
    as_of = datetime.now(UTC)
    items = list(await repository.list_order_items())
    rows = _build_rows(items, as_of)

    metrics = _compute_metrics(rows, as_of)

    state_filter = frozenset(query.state) if query.state else None
    urgency_filter = frozenset(query.urgency) if query.urgency else None
    filtered = [
        row
        for row in rows
        if (state_filter is None or row.summary.state in state_filter)
        and (urgency_filter is None or row.urgency.level in urgency_filter)
    ]
    filtered.sort(key=_sort_key)

    if query.cursor is not None:
        cursor_key = _cursor_sort_key(_decode_cursor(query.cursor))
        filtered = [row for row in filtered if _sort_key(row) > cursor_key]

    page_rows = filtered[: query.limit]
    has_more = len(filtered) > query.limit
    next_cursor = (
        _encode_cursor(
            _CursorKey(
                return_by=page_rows[-1].return_by_value,
                retailer_name=page_rows[-1].order.retailer_name,
                item_id=page_rows[-1].item.id,
            )
        )
        if has_more
        else None
    )

    return DashboardResponse(
        metrics=metrics,
        urgency_legend=_urgency_legend(),
        candidates=[_to_candidate(row) for row in page_rows],
        page=Page(next_cursor=next_cursor),
    )
