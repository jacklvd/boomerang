from datetime import UTC, date, datetime

import pytest

from app.db.mappers import (
    account_from_row,
    account_to_row,
    order_from_row,
    order_item_from_row,
    order_item_to_row,
    order_to_row,
    preference_set_from_row,
    preference_set_to_row,
    return_policy_from_row,
    return_policy_to_row,
    return_summary_from_row,
    return_summary_to_row,
)
from app.db.models import OrderItemRow, ReturnPolicyRow
from app.models import (
    Account,
    FactOrigin,
    HandoffEvidence,
    Money,
    Order,
    OrderItem,
    PolicyEligibility,
    PolicyRule,
    Preference,
    PreferenceSet,
    ReturnPolicy,
    ReturnState,
    ReturnSummary,
    ReturnSummaryUpdateSource,
    SourcedDate,
    SourcedMoney,
)

NOW = datetime(2026, 9, 5, 18, 22, 41, tzinfo=UTC)


def test_simple_records_round_trip_between_domain_and_orm():
    account = Account(
        id="acct_01",
        google_subject="google-01",
        email=None,
        display_name="Sam",
        avatar_url=None,
        created_at=NOW,
        updated_at=NOW,
    )
    order = Order(
        id="order_01",
        account_id=account.id,
        retailer_key="retailer_a",
        retailer_name="Example Retailer",
        retailer_order_reference=None,
        ordered_on=None,
        created_at=NOW,
        updated_at=NOW,
    )
    item = OrderItem(
        id="item_01",
        order_id=order.id,
        description="Trail running shoes",
        variant=None,
        quantity=1,
        price=Money(amount_minor=0, currency="USD"),
        delivered_on=None,
        created_at=NOW,
        updated_at=NOW,
    )

    assert account_from_row(account_to_row(account)) == account
    assert order_from_row(order_to_row(order)) == order
    assert order_item_from_row(order_item_to_row(item)) == item


def test_return_policy_round_trip_preserves_sourced_values_and_rules():
    policy = ReturnPolicy(
        item_id="item_01",
        eligibility=PolicyEligibility.ELIGIBLE,
        return_by=SourcedDate(
            value=date(2026, 9, 12),
            origin=FactOrigin.RETAILER_STATED,
            confidence=None,
        ),
        fee=SourcedMoney(
            value=Money(amount_minor=699, currency="USD"),
            origin=FactOrigin.DERIVED,
            confidence=0.8,
        ),
        rules=(
            PolicyRule(
                id="rule_01",
                text="Keep original packaging.",
                origin=FactOrigin.RETAILER_STATED,
                confidence=None,
            ),
        ),
        version=1,
        updated_at=NOW,
    )
    assert return_policy_from_row(return_policy_to_row(policy)) == policy


def test_nullable_policy_and_preferences_round_trip():
    policy = ReturnPolicy(
        item_id="item_01",
        eligibility=PolicyEligibility.UNKNOWN,
        return_by=None,
        fee=None,
        rules=(),
        version=1,
        updated_at=NOW,
    )
    preferences = PreferenceSet(
        account_id="acct_01",
        values=(Preference.NO_PRINTER, Preference.LOWEST_COST),
        updated_at=NOW,
    )

    assert return_policy_from_row(return_policy_to_row(policy)) == policy
    assert preference_set_from_row(preference_set_to_row(preferences)) == preferences


@pytest.mark.parametrize(
    ("state", "evidence"),
    [
        (ReturnState.NOT_STARTED, None),
        (ReturnState.IN_PROGRESS, None),
        (ReturnState.QR_READY, None),
        (ReturnState.LABEL_READY, None),
        (ReturnState.HANDED_TO_CARRIER, HandoffEvidence.USER_CONFIRMED),
        (ReturnState.COMPLETE, None),
    ],
)
def test_return_summary_states_round_trip(state, evidence):
    source = (
        ReturnSummaryUpdateSource.SYSTEM_INITIALIZATION
        if state is ReturnState.NOT_STARTED
        else ReturnSummaryUpdateSource.USER_CONFIRMED
    )
    summary = ReturnSummary(
        item_id="item_01",
        state=state,
        update_source=source,
        handoff_evidence=evidence,
        observed_at=NOW,
        updated_at=NOW,
    )
    assert return_summary_from_row(return_summary_to_row(summary)) == summary


def test_mapper_rejects_partial_money_columns():
    row = OrderItemRow(
        id="item_01",
        order_id="order_01",
        description="Shoes",
        variant=None,
        quantity=1,
        price_amount_minor=100,
        price_currency=None,
        delivered_on=None,
        created_at=NOW,
        updated_at=NOW,
    )
    with pytest.raises(ValueError, match="price columns"):
        order_item_from_row(row)


def test_mapper_preserves_an_unknown_item_price():
    row = OrderItemRow(
        id="item_01",
        order_id="order_01",
        description="Shoes",
        variant=None,
        quantity=1,
        price_amount_minor=None,
        price_currency=None,
        delivered_on=None,
        created_at=NOW,
        updated_at=NOW,
    )
    assert order_item_from_row(row).price is None


def test_mapper_rejects_partial_sourced_columns():
    row = ReturnPolicyRow(
        item_id="item_01",
        eligibility=PolicyEligibility.UNKNOWN,
        return_by_value=None,
        return_by_origin=None,
        return_by_confidence=0.5,
        fee_amount_minor=None,
        fee_currency=None,
        fee_origin=None,
        fee_confidence=None,
        version=1,
        updated_at=NOW,
    )
    row.rules = []
    with pytest.raises(ValueError, match="deadline columns"):
        return_policy_from_row(row)


def test_mapper_rejects_partial_fee_columns():
    row = ReturnPolicyRow(
        item_id="item_01",
        eligibility=PolicyEligibility.UNKNOWN,
        return_by_value=None,
        return_by_origin=None,
        return_by_confidence=None,
        fee_amount_minor=100,
        fee_currency=None,
        fee_origin=FactOrigin.DERIVED,
        fee_confidence=0.5,
        version=1,
        updated_at=NOW,
    )
    row.rules = []
    with pytest.raises(ValueError, match="fee columns"):
        return_policy_from_row(row)
