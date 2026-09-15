"""One return-candidate's full detail, addressed by item id.

This is the only item-addressed read in the API, which makes it the primary exposure
for cross-account leakage: a client supplies only an item id, never an account id, and
the item table's ``id`` column is globally unique across every account. The repository
this handler receives is already bound to the principal's account (see
``app.api.deps``), and ``ScopedRepository.get_order_item`` answers a foreign item and a
never-existing item through the exact same ``None`` return - this handler must preserve
that by never doing extra work, an extra lookup, or a different log line for one case
that the other would skip. ``not_found_error()`` is the single call site that renders
the result, and it is reached identically from either cause.

The wire models and derivation helpers this route shares with the dashboard route live
in ``app.routes._candidates``.
"""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ScopedRepositoryDep
from app.api.errors import not_found_error
from app.models import PolicyRule
from app.routes._candidates import (
    DatesView,
    ItemView,
    PolicyView,
    ReturnCandidate,
    ReturnSummaryView,
    derive_urgency,
    fee,
    money,
    next_action,
    retailer_ref,
    return_by,
)

router = APIRouter(tags=["items"])


class ReturnCandidateDetail(BaseModel):
    """The full response wrapping one candidate with its snapshot timestamp."""

    generated_at: datetime
    candidate: ReturnCandidate


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
    return_by_fact = return_by(policy)
    urgency = derive_urgency(
        return_by_fact.value if return_by_fact is not None else None, generated_at
    )
    action = next_action(summary.state, policy.eligibility, urgency.level)

    candidate = ReturnCandidate(
        item_id=item.id,
        order_id=item.order_id,
        retailer=retailer_ref(order),
        order_reference=order.retailer_order_reference,
        item=ItemView(
            description=item.description,
            variant=item.variant,
            quantity=item.quantity,
            price=money(item.price_amount_minor, item.price_currency),
        ),
        dates=DatesView(
            ordered_on=order.ordered_on,
            delivered_on=item.delivered_on,
            return_by=return_by_fact,
        ),
        policy=PolicyView(
            eligibility=policy.eligibility,
            fee=fee(policy),
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
        next_action=action,
    )
    return ReturnCandidateDetail(generated_at=generated_at, candidate=candidate)
