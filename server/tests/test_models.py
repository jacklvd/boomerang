from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

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
    UrgencyLevel,
)

NOW = datetime(2026, 9, 5, 18, 22, 41, tzinfo=UTC)


@pytest.mark.parametrize(
    ("enum_type", "expected"),
    [
        (
            ReturnState,
            {
                "not_started",
                "in_progress",
                "qr_ready",
                "label_ready",
                "handed_to_carrier",
                "complete",
            },
        ),
        (
            Preference,
            {
                "lowest_cost",
                "fastest_refund_or_replacement",
                "no_printer",
                "more_sustainable",
            },
        ),
        (PolicyEligibility, {"eligible", "ineligible", "unknown"}),
        (FactOrigin, {"retailer_stated", "derived", "user_confirmed"}),
        (
            ReturnSummaryUpdateSource,
            {"system_initialization", "extension_live_page", "user_confirmed"},
        ),
        (HandoffEvidence, {"user_confirmed", "retailer_observed"}),
        (UrgencyLevel, {"expired", "critical", "soon", "later", "unknown"}),
    ],
)
def test_closed_enum_values_are_exact(enum_type, expected):
    assert {member.value for member in enum_type} == expected


def test_money_accepts_zero_and_serializes_integer_minor_units():
    money = Money(amount_minor=0, currency="USD")
    assert money.model_dump() == {"amount_minor": 0, "currency": "USD"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount_minor", -1),
        ("amount_minor", 1.5),
        ("amount_minor", "100"),
        ("amount_minor", True),
        ("currency", "usd"),
        ("currency", "US"),
        ("currency", "USDD"),
    ],
)
def test_money_rejects_invalid_values(field, value):
    data = {"amount_minor": 100, "currency": "USD"}
    data[field] = value
    with pytest.raises(ValidationError):
        Money.model_validate(data)


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0, None])
def test_sourced_values_accept_confidence_boundaries(confidence):
    sourced_date = SourcedDate(
        value=date(2026, 9, 12),
        origin=FactOrigin.RETAILER_STATED,
        confidence=confidence,
    )
    sourced_money = SourcedMoney(
        value=Money(amount_minor=699, currency="USD"),
        origin=FactOrigin.DERIVED,
        confidence=confidence,
    )
    assert sourced_date.confidence == confidence
    assert sourced_money.confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_sourced_values_reject_out_of_range_confidence(confidence):
    with pytest.raises(ValidationError):
        SourcedDate(
            value=date(2026, 9, 12),
            origin=FactOrigin.DERIVED,
            confidence=confidence,
        )


def test_required_nullable_fields_must_be_present():
    with pytest.raises(ValidationError):
        SourcedDate.model_validate(
            {"value": date(2026, 9, 12), "origin": FactOrigin.RETAILER_STATED},
        )


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        Money.model_validate({"amount_minor": 100, "currency": "USD", "dollars": 1.0})


def make_account(**overrides) -> Account:
    data = {
        "id": "acct_01",
        "google_subject": "google-subject-01",
        "email": "sam@example.com",
        "display_name": "Sam",
        "avatar_url": "https://example.com/avatar.png",
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return Account.model_validate(data)


def test_account_accepts_nullable_profile_fields():
    account = make_account(email=None, display_name=None, avatar_url=None)
    assert account.email is None
    assert account.display_name is None
    assert account.avatar_url is None


@pytest.mark.parametrize("avatar_url", ["http://example.com/a.png", "/avatar.png", "invalid"])
def test_account_requires_absolute_https_avatar_url(avatar_url):
    with pytest.raises(ValidationError, match="absolute HTTPS"):
        make_account(avatar_url=avatar_url)


def test_timestamps_must_be_aware_and_are_normalized_to_utc():
    with pytest.raises(ValidationError, match="UTC offset"):
        make_account(created_at=NOW.replace(tzinfo=None))

    pacific = timezone_from_hours(-7)
    account = make_account(created_at=datetime(2026, 9, 5, 11, 22, 41, tzinfo=pacific))
    assert account.created_at == NOW
    assert account.created_at.tzinfo is UTC


def timezone_from_hours(hours: int):
    return timezone(timedelta(hours=hours))


def make_policy(**overrides) -> ReturnPolicy:
    data = {
        "item_id": "item_01",
        "eligibility": PolicyEligibility.ELIGIBLE,
        "return_by": SourcedDate(
            value=date(2026, 9, 12),
            origin=FactOrigin.RETAILER_STATED,
            confidence=None,
        ),
        "fee": SourcedMoney(
            value=Money(amount_minor=0, currency="USD"),
            origin=FactOrigin.RETAILER_STATED,
            confidence=None,
        ),
        "rules": (
            PolicyRule(
                id="rule_01",
                text="Return in original packaging.",
                origin=FactOrigin.RETAILER_STATED,
                confidence=None,
            ),
        ),
        "version": 1,
        "updated_at": NOW,
    }
    data.update(overrides)
    return ReturnPolicy.model_validate(data)


def test_complete_domain_graph_serializes_expected_fields():
    order = Order(
        id="order_01",
        account_id="acct_01",
        retailer_key="retailer_a",
        retailer_name="Example Retailer",
        retailer_order_reference="ORDER-1001",
        ordered_on=date(2026, 8, 24),
        created_at=NOW,
        updated_at=NOW,
    )
    item = OrderItem(
        id="item_01",
        order_id=order.id,
        description="Trail running shoes",
        variant="Blue / 10",
        quantity=1,
        price=Money(amount_minor=8999, currency="USD"),
        delivered_on=date(2026, 8, 29),
        created_at=NOW,
        updated_at=NOW,
    )
    policy = make_policy()

    assert item.model_dump(mode="json")["price"] == {
        "amount_minor": 8999,
        "currency": "USD",
    }
    assert order.model_dump(mode="json")["ordered_on"] == "2026-08-24"
    assert policy.model_dump(mode="json")["return_by"]["value"] == "2026-09-12"


@pytest.mark.parametrize("quantity", [0, -1])
def test_order_item_quantity_must_be_positive(quantity):
    with pytest.raises(ValidationError):
        OrderItem(
            id="item_01",
            order_id="order_01",
            description="Shoes",
            variant=None,
            quantity=quantity,
            price=None,
            delivered_on=None,
            created_at=NOW,
            updated_at=NOW,
        )


@pytest.mark.parametrize("version", [0, -1])
def test_return_policy_version_must_be_positive(version):
    with pytest.raises(ValidationError):
        make_policy(version=version)


def test_return_policy_rejects_duplicate_rule_ids():
    rule = PolicyRule(
        id="rule_01",
        text="Keep packaging.",
        origin=FactOrigin.DERIVED,
        confidence=0.8,
    )
    with pytest.raises(ValidationError, match="rule identifiers"):
        make_policy(rules=(rule, rule))


def test_preference_set_is_duplicate_free_but_not_priority_ordered():
    preferences = PreferenceSet(
        account_id="acct_01",
        values=(Preference.NO_PRINTER, Preference.LOWEST_COST),
        updated_at=NOW,
    )
    assert set(preferences.values) == {Preference.LOWEST_COST, Preference.NO_PRINTER}

    with pytest.raises(ValidationError, match="must be unique"):
        PreferenceSet(
            account_id="acct_01",
            values=(Preference.NO_PRINTER, Preference.NO_PRINTER),
            updated_at=NOW,
        )


def make_summary(**overrides) -> ReturnSummary:
    data = {
        "item_id": "item_01",
        "state": ReturnState.NOT_STARTED,
        "update_source": ReturnSummaryUpdateSource.SYSTEM_INITIALIZATION,
        "handoff_evidence": None,
        "observed_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return ReturnSummary.model_validate(data)


def test_initial_return_summary_matches_contract():
    assert make_summary().model_dump(mode="json") == {
        "item_id": "item_01",
        "state": "not_started",
        "update_source": "system_initialization",
        "handoff_evidence": None,
        "observed_at": "2026-09-05T18:22:41Z",
        "updated_at": "2026-09-05T18:22:41Z",
    }


def test_system_initialization_cannot_create_later_state():
    with pytest.raises(ValidationError, match="system_initialization"):
        make_summary(state=ReturnState.IN_PROGRESS)


def test_handed_to_carrier_requires_evidence():
    with pytest.raises(ValidationError, match="requires handoff evidence"):
        make_summary(
            state=ReturnState.HANDED_TO_CARRIER,
            update_source=ReturnSummaryUpdateSource.USER_CONFIRMED,
        )


def test_handoff_evidence_is_for_handed_to_carrier_only():
    with pytest.raises(ValidationError, match="valid only"):
        make_summary(
            state=ReturnState.LABEL_READY,
            update_source=ReturnSummaryUpdateSource.EXTENSION_LIVE_PAGE,
            handoff_evidence=HandoffEvidence.USER_CONFIRMED,
        )


@pytest.mark.parametrize("state", [ReturnState.HANDED_TO_CARRIER, ReturnState.COMPLETE])
def test_reserved_return_states_remain_representable(state):
    evidence = HandoffEvidence.RETAILER_OBSERVED if state is ReturnState.HANDED_TO_CARRIER else None
    summary = make_summary(
        state=state,
        update_source=ReturnSummaryUpdateSource.USER_CONFIRMED,
        handoff_evidence=evidence,
    )
    assert summary.state is state
