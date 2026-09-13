"""One return-candidate's full detail, addressed by item id.

This is the only item-addressed read in the API, which makes it the primary exposure
for cross-account leakage: a client supplies only an item id, never an account id, and
the item table's ``id`` column is globally unique across every account. The repository
this handler receives is already bound to the principal's account (see
``app.api.deps``), and ``ScopedRepository.get_order_item`` answers a foreign item and a
never-existing item through the exact same ``None`` return — this handler must preserve
that by never doing extra work, an extra lookup, or a different log line for one case
that the other would skip. ``not_found_error()`` is the single call site that renders
the result, and it is reached identically from either cause.
"""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Final

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ScopedRepositoryDep
from app.api.errors import not_found_error
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

router = APIRouter(tags=["items"])

# The v1 urgency thresholds shown in the contract's own worked example: a deadline that
# has already passed is "expired"; 0-2 days out is "critical"; 3-7 days out is "soon";
# 8 or more is "later". A missing deadline is "unknown" and carries no day count. The
# contract calls these "server configuration" rather than freezing the numbers
# themselves, but there is no shared configuration surface yet and this route may not
# add one, so the worked thresholds are reproduced here as the current v1 values.
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
    """The shared candidate shape used by the dashboard list and this detail view."""

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


class ReturnCandidateDetail(BaseModel):
    """The full response wrapping one candidate with its snapshot timestamp."""

    generated_at: datetime
    candidate: ReturnCandidate


def _money(amount_minor: int | None, currency: str | None) -> Money | None:
    """Build a wire ``Money`` from a paired minor-amount/currency column pair.

    The two columns are constrained together at the database (both present or both
    absent), but that constraint is not visible to the type checker, so both are
    checked here rather than trusting one to imply the other.
    """
    if amount_minor is None or currency is None:
        return None
    return Money(amount_minor=amount_minor, currency=currency)


def _return_by(policy: ReturnPolicyRow) -> SourcedDate | None:
    """Build the policy's ``return_by`` fact, or ``None`` when the deadline is unknown."""
    value = policy.return_by_value
    origin = policy.return_by_origin
    if value is None or origin is None:
        return None
    return SourcedDate(value=value, origin=origin, confidence=policy.return_by_confidence)


def _fee(policy: ReturnPolicyRow) -> SourcedMoney | None:
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


def _derive_urgency(return_by: date | None, as_of: datetime) -> Urgency:
    """Derive urgency level and remaining days from a deadline, as of ``as_of``.

    A missing deadline is always ``unknown`` with no day count. Otherwise the day
    count may be negative, meaning the deadline has already passed.
    """
    if return_by is None:
        return Urgency(level=UrgencyLevel.UNKNOWN, days_remaining=None)
    days_remaining = (return_by - as_of.date()).days
    if days_remaining < 0:
        level = UrgencyLevel.EXPIRED
    elif days_remaining <= CRITICAL_MAX_DAYS:
        level = UrgencyLevel.CRITICAL
    elif days_remaining <= SOON_MAX_DAYS:
        level = UrgencyLevel.SOON
    else:
        level = UrgencyLevel.LATER
    return Urgency(level=level, days_remaining=days_remaining)


def _next_action(
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


def _retailer_ref(order: OrderRow) -> RetailerRef:
    """Build the retailer reference nested under a return candidate."""
    return RetailerRef(key=order.retailer_key, name=order.retailer_name)


@router.get("/items/{item_id}")
async def read_item(item_id: str, repository: ScopedRepositoryDep) -> ReturnCandidateDetail:
    """Return one return candidate's full detail for the signed-in account.

    ``item_id`` is a client-supplied string that is never an account id: it is looked
    up only through the account-scoped repository, which answers a foreign item and a
    genuinely-absent item identically with ``None``. This function raises
    ``not_found_error()`` from that single result with no further lookup and no branch
    that would tell the two cases apart, so the two responses stay indistinguishable.
    """
    item = await repository.get_order_item(item_id)
    if item is None:
        raise not_found_error()

    order = await repository.get_order(item.order_id)
    if order is None:
        # Every stored item belongs to a stored order in the same account by
        # construction (see the composite foreign key in app.db.models). Reaching here
        # would mean that invariant broke, not that the caller did anything wrong.
        raise not_found_error()

    policy = await repository.get_return_policy(item_id)
    if policy is None:
        # Ingestion creates an item's policy and initial summary together with the
        # item itself, so every stored item has exactly one of each. Same defensive
        # posture as the order check above.
        raise not_found_error()

    summary = await repository.get_return_summary(item_id)
    if summary is None:
        raise not_found_error()

    generated_at = datetime.now(UTC)
    return_by = _return_by(policy)
    urgency = _derive_urgency(return_by.value if return_by is not None else None, generated_at)
    next_action = _next_action(summary.state, policy.eligibility, urgency.level)

    candidate = ReturnCandidate(
        item_id=item.id,
        order_id=item.order_id,
        retailer=_retailer_ref(order),
        order_reference=order.retailer_order_reference,
        item=ItemView(
            description=item.description,
            variant=item.variant,
            quantity=item.quantity,
            price=_money(item.price_amount_minor, item.price_currency),
        ),
        dates=DatesView(
            ordered_on=order.ordered_on,
            delivered_on=item.delivered_on,
            return_by=return_by,
        ),
        policy=PolicyView(
            eligibility=policy.eligibility,
            fee=_fee(policy),
            rules=[
                PolicyRule(
                    id=rule.id, text=rule.text, origin=rule.origin, confidence=rule.confidence
                )
                for rule in policy.rules
            ],
        ),
        urgency=urgency,
        return_summary=ReturnSummaryView(
            state=summary.state,
            update_source=summary.update_source,
            handoff_evidence=summary.handoff_evidence,
            observed_at=summary.observed_at,
            updated_at=summary.updated_at,
        ),
        next_action=next_action,
    )
    return ReturnCandidateDetail(generated_at=generated_at, candidate=candidate)
