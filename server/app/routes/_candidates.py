"""Shared return-candidate wire models and derivation helpers.

``GET /v1/items/{item_id}`` and ``GET /v1/dashboard`` both project the same
underlying rows into the same ``ReturnCandidate`` shape (see
``design/boomerang-data-model.md`` section 7.4): one candidate nested under a
snapshot timestamp for the item-detail route, many candidates alongside
account-wide metrics for the dashboard. This module is the one place that
shape and its derivation rules live, so the two routes cannot drift apart.

The module itself is the private boundary - ruff's ``SLF001`` forbids importing an
underscore-prefixed name across modules, so every name defined here is public; only
the module's own leading underscore marks it as an internal implementation detail of
``app.routes``, not part of any public API.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Final

from pydantic import BaseModel

from app.db.models import OrderRow, ReturnPolicyRow
from app.models import (
    HandoffEvidence,
    Money,
    PolicyEligibility,
    PolicyRule,
    ReturnState,
    ReturnSummaryUpdateSource,
    SourcedDate,
    SourcedMoney,
    UrgencyLevel,
)

# The v1 urgency thresholds shown in the contract's own worked example: a deadline that
# has already passed is "expired"; 0-2 days out is "critical"; 3-7 days out is "soon";
# 8 or more is "later". A missing deadline is "unknown" and carries no day count. The
# contract calls these "server configuration" rather than freezing the numbers
# themselves, but there is no shared configuration surface yet, so the worked
# thresholds are reproduced here as the current v1 values. Both the item-detail route
# and the dashboard route read these two constants from this one module so neither can
# drift from the other.
CRITICAL_MAX_DAYS: Final[int] = 2
SOON_MAX_DAYS: Final[int] = 7


class NextActionCode(StrEnum):
    """The closed vocabulary for :class:`NextAction`'s ``code`` field."""

    START_RETURN = "start_return"
    FOCUS_ACTIVE_RETURN = "focus_active_return"
    OPEN_RETAILER_RESULT = "open_retailer_result"
    MANUAL_REQUIRED = "manual_required"
    NONE = "none"


class RetailerRef(BaseModel):
    """The retailer an order belongs to, as it goes on the wire."""

    key: str
    name: str


class ItemView(BaseModel):
    """The item-level facts nested under a return candidate."""

    description: str
    variant: str | None
    quantity: int
    price: Money | None


class DatesView(BaseModel):
    """The dates nested under a return candidate."""

    ordered_on: date | None
    delivered_on: date | None
    return_by: SourcedDate | None


class PolicyView(BaseModel):
    """The current return policy nested under a return candidate."""

    eligibility: PolicyEligibility
    fee: SourcedMoney | None
    rules: list[PolicyRule]


class Urgency(BaseModel):
    """Deadline urgency derived as of the enclosing response's snapshot time."""

    level: UrgencyLevel
    days_remaining: int | None


class ReturnSummaryView(BaseModel):
    """The current return-progress milestone nested under a return candidate."""

    state: ReturnState
    update_source: ReturnSummaryUpdateSource
    handoff_evidence: HandoffEvidence | None
    observed_at: datetime
    updated_at: datetime


class NextAction(BaseModel):
    """The advisory next step derived for a return candidate."""

    code: NextActionCode
    label: str


class ReturnCandidate(BaseModel):
    """The shared candidate shape used by the dashboard list and the detail view."""

    item_id: str
    order_id: str
    retailer: RetailerRef
    order_reference: str | None
    item: ItemView
    dates: DatesView
    policy: PolicyView
    urgency: Urgency
    return_summary: ReturnSummaryView
    next_action: NextAction


def money(amount_minor: int | None, currency: str | None) -> Money | None:
    """Build a wire ``Money`` from a paired minor-amount/currency column pair.

    The two columns are constrained together at the database (both present or both
    absent), but that constraint is not visible to the type checker, so both are
    checked here rather than trusting one to imply the other.
    """
    if amount_minor is None or currency is None:
        return None
    return Money(amount_minor=amount_minor, currency=currency)


def return_by(policy: ReturnPolicyRow) -> SourcedDate | None:
    """Build the policy's ``return_by`` fact, or ``None`` when the deadline is unknown."""
    value = policy.return_by_value
    origin = policy.return_by_origin
    if value is None or origin is None:
        return None
    return SourcedDate(value=value, origin=origin, confidence=policy.return_by_confidence)


def fee(policy: ReturnPolicyRow) -> SourcedMoney | None:
    """Build the policy's return fee, or ``None`` when no fee fact is stored."""
    amount_minor = policy.fee_amount_minor
    currency = policy.fee_currency
    origin = policy.fee_origin
    if amount_minor is None or currency is None or origin is None:
        return None
    return SourcedMoney(
        value=Money(amount_minor=amount_minor, currency=currency),
        origin=origin,
        confidence=policy.fee_confidence,
    )


def derive_urgency(return_by_value: date | None, as_of: datetime) -> Urgency:
    """Derive urgency level and remaining days from a deadline, as of ``as_of``.

    A missing deadline is always ``unknown`` with no day count. Otherwise the day
    count may be negative, meaning the deadline has already passed.
    """
    if return_by_value is None:
        return Urgency(level=UrgencyLevel.UNKNOWN, days_remaining=None)
    days_remaining = (return_by_value - as_of.date()).days
    if days_remaining < 0:
        level = UrgencyLevel.EXPIRED
    elif days_remaining <= CRITICAL_MAX_DAYS:
        level = UrgencyLevel.CRITICAL
    elif days_remaining <= SOON_MAX_DAYS:
        level = UrgencyLevel.SOON
    else:
        level = UrgencyLevel.LATER
    return Urgency(level=level, days_remaining=days_remaining)


def next_action(
    state: ReturnState, eligibility: PolicyEligibility, urgency_level: UrgencyLevel
) -> NextAction:
    """Derive the advisory next action using the contract's first-match precedence.

    Workflow progress (``qr_ready``, ``label_ready``, ``in_progress``) always wins over
    policy or deadline projections, because it records a validated return milestone
    rather than a projection. ``not_started`` is the only state that consults
    eligibility and urgency at all, and the three rules for it are mutually exclusive
    and exhaustive over every remaining combination.
    """
    if state in (ReturnState.QR_READY, ReturnState.LABEL_READY):
        return NextAction(code=NextActionCode.OPEN_RETAILER_RESULT, label="Open return result")
    if state is ReturnState.IN_PROGRESS:
        return NextAction(code=NextActionCode.FOCUS_ACTIVE_RETURN, label="Continue return")
    if state is ReturnState.NOT_STARTED:
        if eligibility is PolicyEligibility.INELIGIBLE:
            return NextAction(code=NextActionCode.MANUAL_REQUIRED, label="Continue manually")
        if urgency_level is UrgencyLevel.EXPIRED:
            return NextAction(code=NextActionCode.MANUAL_REQUIRED, label="Continue manually")
        return NextAction(code=NextActionCode.START_RETURN, label="Start return")
    # The only remaining states are handed_to_carrier and complete.
    return NextAction(code=NextActionCode.NONE, label="No action")


def retailer_ref(order: OrderRow) -> RetailerRef:
    """Build the retailer reference nested under a return candidate."""
    return RetailerRef(key=order.retailer_key, name=order.retailer_name)
