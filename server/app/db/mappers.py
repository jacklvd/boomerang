"""Pure conversions between validated domain records and fully loaded ORM rows."""

from app.db.models import (
    AccountRow,
    OrderItemRow,
    OrderRow,
    PolicyRuleRow,
    PreferenceSetRow,
    PreferenceValueRow,
    ReturnPolicyRow,
    ReturnSummaryRow,
)
from app.models import (
    Account,
    Money,
    Order,
    OrderItem,
    PolicyRule,
    PreferenceSet,
    ReturnPolicy,
    ReturnSummary,
    SourcedDate,
    SourcedMoney,
)


def account_to_row(account: Account) -> AccountRow:
    """Convert an account domain record to a new ORM row."""
    return AccountRow(**account.model_dump())


def account_from_row(row: AccountRow) -> Account:
    """Convert a fully loaded account row to its domain record."""
    return Account.model_validate(
        {
            "id": row.id,
            "google_subject": row.google_subject,
            "email": row.email,
            "display_name": row.display_name,
            "avatar_url": row.avatar_url,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        },
    )


def order_to_row(order: Order) -> OrderRow:
    """Convert an order domain record to a new ORM row."""
    return OrderRow(**order.model_dump())


def order_from_row(row: OrderRow) -> Order:
    """Convert a fully loaded order row to its domain record."""
    return Order.model_validate(
        {
            "id": row.id,
            "account_id": row.account_id,
            "retailer_key": row.retailer_key,
            "retailer_name": row.retailer_name,
            "retailer_order_reference": row.retailer_order_reference,
            "ordered_on": row.ordered_on,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        },
    )


def order_item_to_row(item: OrderItem) -> OrderItemRow:
    """Convert an order-item domain record to a flattened ORM row."""
    return OrderItemRow(
        id=item.id,
        order_id=item.order_id,
        description=item.description,
        variant=item.variant,
        quantity=item.quantity,
        price_amount_minor=item.price.amount_minor if item.price else None,
        price_currency=item.price.currency if item.price else None,
        delivered_on=item.delivered_on,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def order_item_from_row(row: OrderItemRow) -> OrderItem:
    """Convert an order-item row to a validated domain record."""
    price = None
    price_amount = row.price_amount_minor
    price_currency = row.price_currency
    has_price_amount = price_amount is not None
    has_price_currency = price_currency is not None
    if has_price_amount != has_price_currency:
        msg = "order-item price columns are internally inconsistent"
        raise ValueError(msg)
    if price_amount is not None and price_currency is not None:
        price = Money(amount_minor=price_amount, currency=price_currency)
    return OrderItem(
        id=row.id,
        order_id=row.order_id,
        description=row.description,
        variant=row.variant,
        quantity=row.quantity,
        price=price,
        delivered_on=row.delivered_on,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_rule_to_row(item_id: str, rule: PolicyRule) -> PolicyRuleRow:
    return PolicyRuleRow(
        item_id=item_id,
        id=rule.id,
        text=rule.text,
        origin=rule.origin,
        confidence=rule.confidence,
    )


def return_policy_to_row(policy: ReturnPolicy) -> ReturnPolicyRow:
    """Convert a return policy and its rules to new ORM rows."""
    row = ReturnPolicyRow(
        item_id=policy.item_id,
        eligibility=policy.eligibility,
        return_by_value=policy.return_by.value if policy.return_by else None,
        return_by_origin=policy.return_by.origin if policy.return_by else None,
        return_by_confidence=policy.return_by.confidence if policy.return_by else None,
        fee_amount_minor=policy.fee.value.amount_minor if policy.fee else None,
        fee_currency=policy.fee.value.currency if policy.fee else None,
        fee_origin=policy.fee.origin if policy.fee else None,
        fee_confidence=policy.fee.confidence if policy.fee else None,
        version=policy.version,
        updated_at=policy.updated_at,
    )
    row.rules = [_policy_rule_to_row(policy.item_id, rule) for rule in policy.rules]
    return row


def return_policy_from_row(row: ReturnPolicyRow) -> ReturnPolicy:
    """Convert a fully loaded return-policy row and rules to the domain."""
    return_by = None
    return_by_value = row.return_by_value
    return_by_origin = row.return_by_origin
    has_return_by_value = return_by_value is not None
    has_return_by_origin = return_by_origin is not None
    if has_return_by_value != has_return_by_origin or (
        not has_return_by_value and row.return_by_confidence is not None
    ):
        msg = "return-policy deadline columns are internally inconsistent"
        raise ValueError(msg)
    if return_by_value is not None and return_by_origin is not None:
        return_by = SourcedDate(
            value=return_by_value,
            origin=return_by_origin,
            confidence=row.return_by_confidence,
        )
    fee = None
    fee_amount = row.fee_amount_minor
    fee_currency = row.fee_currency
    fee_origin = row.fee_origin
    fee_presence = (
        fee_amount is not None,
        fee_currency is not None,
        fee_origin is not None,
    )
    if len(set(fee_presence)) != 1 or (not fee_presence[0] and row.fee_confidence is not None):
        msg = "return-policy fee columns are internally inconsistent"
        raise ValueError(msg)
    if fee_amount is not None and fee_currency is not None and fee_origin is not None:
        fee = SourcedMoney(
            value=Money(amount_minor=fee_amount, currency=fee_currency),
            origin=fee_origin,
            confidence=row.fee_confidence,
        )
    rules = tuple(
        PolicyRule(
            id=rule.id,
            text=rule.text,
            origin=rule.origin,
            confidence=rule.confidence,
        )
        for rule in row.rules
    )
    return ReturnPolicy(
        item_id=row.item_id,
        eligibility=row.eligibility,
        return_by=return_by,
        fee=fee,
        rules=rules,
        version=row.version,
        updated_at=row.updated_at,
    )


def preference_set_to_row(preferences: PreferenceSet) -> PreferenceSetRow:
    """Convert a preference set and its values to new ORM rows."""
    row = PreferenceSetRow(
        account_id=preferences.account_id,
        updated_at=preferences.updated_at,
    )
    row.values = [
        PreferenceValueRow(account_id=preferences.account_id, value=value)
        for value in preferences.values
    ]
    return row


def preference_set_from_row(row: PreferenceSetRow) -> PreferenceSet:
    """Convert a fully loaded preference-set row to the domain."""
    return PreferenceSet(
        account_id=row.account_id,
        values=tuple(value.value for value in row.values),
        updated_at=row.updated_at,
    )


def return_summary_to_row(summary: ReturnSummary) -> ReturnSummaryRow:
    """Convert a return summary domain record to a new ORM row."""
    return ReturnSummaryRow(**summary.model_dump())


def return_summary_from_row(row: ReturnSummaryRow) -> ReturnSummary:
    """Convert a return-summary row to a validated domain record."""
    return ReturnSummary.model_validate(
        {
            "item_id": row.item_id,
            "state": row.state,
            "update_source": row.update_source,
            "handoff_evidence": row.handoff_evidence,
            "observed_at": row.observed_at,
            "updated_at": row.updated_at,
        },
    )
