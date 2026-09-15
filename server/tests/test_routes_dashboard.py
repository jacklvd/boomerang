"""Tests for ``GET /v1/dashboard``.

The route's central property is that ``metrics`` is computed over every item the
account owns, while ``state``/``urgency`` filters and pagination only ever narrow
``candidates``. Most tests below build a small fixed set of items through
``_dashboard_item`` and drive the route through ``StubRepository.list_order_items``,
mirroring the stub-repository pattern ``test_routes_items.py`` uses for the same reason:
these are route-level tests that should not depend on a real database.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models import OrderItemRow, OrderRow, ReturnPolicyRow, ReturnSummaryRow
from app.main import app as production_app
from app.models import (
    FactOrigin,
    PolicyEligibility,
    ReturnState,
    ReturnSummaryUpdateSource,
)
from app.routes import api_router

TIMESTAMP = datetime(2026, 9, 8, 16, 30, tzinfo=UTC)
TODAY = datetime.now(UTC).date()


@dataclass(frozen=True, kw_only=True)
class ItemSpec:
    """The overridable fields of a canned dashboard item, grouped to keep
    ``_dashboard_item`` itself down to a single parameter."""

    item_id: str = "item_1"
    account_id: str = "acct_test"
    retailer_name: str = "Acme"
    return_by_value: date | None = None
    eligibility: PolicyEligibility = PolicyEligibility.ELIGIBLE
    state: ReturnState = ReturnState.NOT_STARTED
    price_amount_minor: int | None = 2500
    price_currency: str | None = "USD"
    has_policy: bool = True
    has_summary: bool = True


def _dashboard_item(spec: ItemSpec | None = None) -> OrderItemRow:
    """Build one fully wired ``OrderItemRow``, its order, policy and summary attached.

    The relationships are set directly on the Python object rather than through a
    session, exactly as ``test_routes_items.py`` does for its own canned rows - these
    objects are never queried, only handed straight to a stub repository.
    """
    spec = spec if spec is not None else ItemSpec()
    item = OrderItemRow(
        account_id=spec.account_id,
        id=spec.item_id,
        order_id=f"order_{spec.item_id}",
        description="Wireless Mouse",
        variant=None,
        quantity=1,
        price_amount_minor=spec.price_amount_minor,
        price_currency=spec.price_currency,
        delivered_on=date(2026, 9, 5),
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    item.order = OrderRow(
        id=item.order_id,
        account_id=spec.account_id,
        retailer_key=spec.retailer_name.lower(),
        retailer_name=spec.retailer_name,
        retailer_order_reference="REF-1",
        ordered_on=date(2026, 9, 1),
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    if spec.has_policy:
        policy = ReturnPolicyRow(
            account_id=spec.account_id,
            item_id=spec.item_id,
            eligibility=spec.eligibility,
            return_by_value=spec.return_by_value,
            return_by_origin=FactOrigin.RETAILER_STATED if spec.return_by_value else None,
            return_by_confidence=0.9 if spec.return_by_value else None,
            fee_amount_minor=None,
            fee_currency=None,
            fee_origin=None,
            fee_confidence=None,
            version=1,
            updated_at=TIMESTAMP,
        )
        policy.rules = []
        item.return_policy = policy
    else:
        item.return_policy = None
    if spec.has_summary:
        item.return_summary = ReturnSummaryRow(
            account_id=spec.account_id,
            item_id=spec.item_id,
            state=spec.state,
            update_source=ReturnSummaryUpdateSource.SYSTEM_INITIALIZATION,
            handoff_evidence=None,
            observed_at=TIMESTAMP,
            updated_at=TIMESTAMP,
        )
    else:
        item.return_summary = None
    return item


class StubRepository:
    """Answers the one read ``read_dashboard`` makes: every account item, ready-loaded."""

    def __init__(self, items: list[OrderItemRow]) -> None:
        self._items = items

    async def list_order_items(self) -> list[OrderItemRow]:
        return self._items


# ---------------------------------------------------------------------------
# Empty account
# ---------------------------------------------------------------------------


def test_empty_account_returns_zeroed_metrics_and_empty_candidates(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    serve_repository(StubRepository([]))

    response = TestClient(api_app).get("/v1/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["candidates"] == []
    assert body["page"] == {"next_cursor": None}
    assert body["metrics"]["closing_soon_count"] == 0
    assert body["metrics"]["in_progress_count"] == 0
    assert body["metrics"]["carrier_handoff_count"] == 0
    assert body["metrics"]["returnable_value_by_currency"] == []
    assert len(body["urgency_legend"]) == 5


# ---------------------------------------------------------------------------
# Metrics stay account-wide regardless of filters
# ---------------------------------------------------------------------------


def test_metrics_are_account_wide_while_state_filter_narrows_candidates(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    items = [
        _dashboard_item(ItemSpec(item_id="item_active", state=ReturnState.IN_PROGRESS)),
        _dashboard_item(ItemSpec(item_id="item_carrier", state=ReturnState.HANDED_TO_CARRIER)),
        _dashboard_item(ItemSpec(item_id="item_not_started", state=ReturnState.NOT_STARTED)),
    ]
    serve_repository(StubRepository(items))

    unfiltered = TestClient(api_app).get("/v1/dashboard")
    filtered = TestClient(api_app).get("/v1/dashboard", params={"state": "in_progress"})

    # ``as_of`` is a fresh timestamp on every request, so it is excluded from the
    # otherwise-exact comparison rather than making the two calls share one clock tick.
    assert {**unfiltered.json()["metrics"], "as_of": None} == {
        **filtered.json()["metrics"],
        "as_of": None,
    }
    assert unfiltered.json()["metrics"]["in_progress_count"] == 1
    assert unfiltered.json()["metrics"]["carrier_handoff_count"] == 1
    assert len(unfiltered.json()["candidates"]) == 3
    filtered_ids = {c["item_id"] for c in filtered.json()["candidates"]}
    assert filtered_ids == {"item_active"}


def test_metrics_are_account_wide_while_urgency_filter_narrows_candidates(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    items = [
        _dashboard_item(
            ItemSpec(item_id="item_critical", return_by_value=TODAY + timedelta(days=1))
        ),
        _dashboard_item(ItemSpec(item_id="item_later", return_by_value=TODAY + timedelta(days=30))),
    ]
    serve_repository(StubRepository(items))

    unfiltered = TestClient(api_app).get("/v1/dashboard")
    filtered = TestClient(api_app).get("/v1/dashboard", params={"urgency": "critical"})

    # ``as_of`` is a fresh timestamp on every request, so it is excluded from the
    # otherwise-exact comparison rather than making the two calls share one clock tick.
    assert {**unfiltered.json()["metrics"], "as_of": None} == {
        **filtered.json()["metrics"],
        "as_of": None,
    }
    filtered_ids = {c["item_id"] for c in filtered.json()["candidates"]}
    assert filtered_ids == {"item_critical"}


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------


def test_sort_orders_known_deadlines_then_unknown_last_with_ties_broken_by_retailer_then_id(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    items = [
        _dashboard_item(
            ItemSpec(item_id="item_unknown", retailer_name="Zeta", return_by_value=None)
        ),
        _dashboard_item(
            ItemSpec(
                item_id="item_expired",
                retailer_name="Acme",
                return_by_value=TODAY - timedelta(days=5),
            )
        ),
        _dashboard_item(
            ItemSpec(
                item_id="item_tie_b",
                retailer_name="Beta",
                return_by_value=TODAY + timedelta(days=10),
            )
        ),
        _dashboard_item(
            ItemSpec(
                item_id="item_tie_a",
                retailer_name="Alpha",
                return_by_value=TODAY + timedelta(days=10),
            )
        ),
    ]
    serve_repository(StubRepository(items))

    response = TestClient(api_app).get("/v1/dashboard", params={"limit": 100})

    ids_in_order = [c["item_id"] for c in response.json()["candidates"]]
    assert ids_in_order == ["item_expired", "item_tie_a", "item_tie_b", "item_unknown"]


# ---------------------------------------------------------------------------
# closing_soon_count predicate
# ---------------------------------------------------------------------------


class _ClosingSoonCase(NamedTuple):
    return_by_value: date | None
    eligibility: PolicyEligibility
    state: ReturnState
    expected_counted: bool


@pytest.mark.parametrize(
    "case",
    [
        _ClosingSoonCase(
            return_by_value=TODAY + timedelta(days=0),
            eligibility=PolicyEligibility.ELIGIBLE,
            state=ReturnState.NOT_STARTED,
            expected_counted=True,
        ),
        _ClosingSoonCase(
            return_by_value=TODAY + timedelta(days=7),
            eligibility=PolicyEligibility.ELIGIBLE,
            state=ReturnState.NOT_STARTED,
            expected_counted=True,
        ),
        _ClosingSoonCase(
            return_by_value=TODAY + timedelta(days=7),
            eligibility=PolicyEligibility.UNKNOWN,
            state=ReturnState.NOT_STARTED,
            expected_counted=True,
        ),
        _ClosingSoonCase(
            return_by_value=TODAY + timedelta(days=8),
            eligibility=PolicyEligibility.ELIGIBLE,
            state=ReturnState.NOT_STARTED,
            expected_counted=False,
        ),
        _ClosingSoonCase(
            return_by_value=TODAY - timedelta(days=1),
            eligibility=PolicyEligibility.ELIGIBLE,
            state=ReturnState.NOT_STARTED,
            expected_counted=False,
        ),
        _ClosingSoonCase(
            return_by_value=None,
            eligibility=PolicyEligibility.ELIGIBLE,
            state=ReturnState.NOT_STARTED,
            expected_counted=False,
        ),
        _ClosingSoonCase(
            return_by_value=TODAY + timedelta(days=1),
            eligibility=PolicyEligibility.INELIGIBLE,
            state=ReturnState.NOT_STARTED,
            expected_counted=False,
        ),
        _ClosingSoonCase(
            return_by_value=TODAY + timedelta(days=1),
            eligibility=PolicyEligibility.ELIGIBLE,
            state=ReturnState.HANDED_TO_CARRIER,
            expected_counted=False,
        ),
        _ClosingSoonCase(
            return_by_value=TODAY + timedelta(days=1),
            eligibility=PolicyEligibility.ELIGIBLE,
            state=ReturnState.COMPLETE,
            expected_counted=False,
        ),
    ],
)
def test_closing_soon_count_predicate_branches(api_app, sign_in, serve_repository, case):
    sign_in("acct_test")
    serve_repository(
        StubRepository(
            [
                _dashboard_item(
                    ItemSpec(
                        return_by_value=case.return_by_value,
                        eligibility=case.eligibility,
                        state=case.state,
                    )
                )
            ]
        )
    )

    response = TestClient(api_app).get("/v1/dashboard")

    assert response.json()["metrics"]["closing_soon_count"] == (1 if case.expected_counted else 0)


# ---------------------------------------------------------------------------
# returnable_value_by_currency ordering
# ---------------------------------------------------------------------------


def test_returnable_value_by_currency_is_sorted_by_currency_code_ascending(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    items = [
        _dashboard_item(
            ItemSpec(item_id="item_usd", price_amount_minor=1000, price_currency="USD")
        ),
        _dashboard_item(ItemSpec(item_id="item_eur", price_amount_minor=500, price_currency="EUR")),
        _dashboard_item(ItemSpec(item_id="item_aud", price_amount_minor=200, price_currency="AUD")),
    ]
    serve_repository(StubRepository(items))

    response = TestClient(api_app).get("/v1/dashboard")

    currencies = [
        entry["currency"] for entry in response.json()["metrics"]["returnable_value_by_currency"]
    ]
    assert currencies == ["AUD", "EUR", "USD"]


def test_returnable_value_excludes_unknown_price_rather_than_treating_it_as_zero(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    items = [
        _dashboard_item(
            ItemSpec(item_id="item_known", price_amount_minor=1000, price_currency="USD")
        ),
        _dashboard_item(
            ItemSpec(item_id="item_unknown_price", price_amount_minor=None, price_currency=None)
        ),
    ]
    serve_repository(StubRepository(items))

    response = TestClient(api_app).get("/v1/dashboard")

    values = response.json()["metrics"]["returnable_value_by_currency"]
    assert values == [{"amount_minor": 1000, "currency": "USD"}]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_pagination_crosses_a_page_boundary_and_the_final_page_has_a_null_cursor(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    items = [
        _dashboard_item(
            ItemSpec(
                item_id=f"item_{i}",
                retailer_name="Acme",
                return_by_value=TODAY + timedelta(days=i),
            )
        )
        for i in range(3)
    ]
    serve_repository(StubRepository(items))
    client = TestClient(api_app)

    first_page = client.get("/v1/dashboard", params={"limit": 2})
    assert first_page.status_code == 200
    first_ids = [c["item_id"] for c in first_page.json()["candidates"]]
    assert first_ids == ["item_0", "item_1"]
    next_cursor = first_page.json()["page"]["next_cursor"]
    assert next_cursor is not None

    second_page = client.get("/v1/dashboard", params={"limit": 2, "cursor": next_cursor})
    assert second_page.status_code == 200
    second_ids = [c["item_id"] for c in second_page.json()["candidates"]]
    assert second_ids == ["item_2"]
    assert second_page.json()["page"]["next_cursor"] is None


def test_malformed_cursor_returns_a_422_rather_than_a_500_or_a_silent_reset(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    serve_repository(StubRepository([_dashboard_item()]))

    response = TestClient(api_app).get("/v1/dashboard", params={"cursor": "not-a-valid-cursor!!!"})

    assert response.status_code == 422
    assert response.json()["reason"] == "validation_failed"


def _encode_test_cursor(payload: object) -> str:
    """Base64url-encode an arbitrary JSON payload the same way the route's own cursor
    does, so tests can drive shapes the route itself would never produce."""
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@pytest.mark.parametrize(
    "payload",
    [
        ["not", "a", "json", "object"],
        {"return_by": 20260101, "retailer_name": "Acme", "item_id": "item_1"},
        {"return_by": None, "retailer_name": 1, "item_id": "item_1"},
        {"return_by": None, "retailer_name": "Acme", "item_id": 1},
    ],
)
def test_a_validly_encoded_but_wrong_shaped_cursor_returns_a_422(
    api_app, sign_in, serve_repository, payload
):
    sign_in("acct_test")
    serve_repository(StubRepository([_dashboard_item()]))

    cursor = _encode_test_cursor(payload)
    response = TestClient(api_app).get("/v1/dashboard", params={"cursor": cursor})

    assert response.status_code == 422
    assert response.json()["reason"] == "validation_failed"


# ---------------------------------------------------------------------------
# Unrecognized query values
# ---------------------------------------------------------------------------


def test_unrecognized_sort_value_returns_422(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(StubRepository([]))

    response = TestClient(api_app).get("/v1/dashboard", params={"sort": "cheapest_first"})

    assert response.status_code == 422
    assert response.json()["reason"] == "validation_failed"


def test_unrecognized_state_value_returns_422(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(StubRepository([]))

    response = TestClient(api_app).get("/v1/dashboard", params={"state": "not_a_real_state"})

    assert response.status_code == 422
    assert response.json()["reason"] == "validation_failed"


def test_unrecognized_urgency_value_returns_422(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(StubRepository([]))

    response = TestClient(api_app).get("/v1/dashboard", params={"urgency": "extremely_urgent"})

    assert response.status_code == 422
    assert response.json()["reason"] == "validation_failed"


def test_limit_out_of_range_returns_422(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(StubRepository([]))

    response = TestClient(api_app).get("/v1/dashboard", params={"limit": 0})

    assert response.status_code == 422
    assert response.json()["reason"] == "validation_failed"


# ---------------------------------------------------------------------------
# Rows missing a policy or a return summary are skipped, not fatal
# ---------------------------------------------------------------------------


def test_item_missing_a_policy_is_skipped_from_candidates_and_metrics(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    items = [
        _dashboard_item(ItemSpec(item_id="item_complete", state=ReturnState.IN_PROGRESS)),
        _dashboard_item(ItemSpec(item_id="item_no_policy", has_policy=False)),
    ]
    serve_repository(StubRepository(items))

    response = TestClient(api_app).get("/v1/dashboard")

    body = response.json()
    assert response.status_code == 200
    assert [c["item_id"] for c in body["candidates"]] == ["item_complete"]
    assert body["metrics"]["in_progress_count"] == 1


def test_item_missing_a_return_summary_is_skipped_from_candidates_and_metrics(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    items = [
        _dashboard_item(ItemSpec(item_id="item_complete", state=ReturnState.IN_PROGRESS)),
        _dashboard_item(ItemSpec(item_id="item_no_summary", has_summary=False)),
    ]
    serve_repository(StubRepository(items))

    response = TestClient(api_app).get("/v1/dashboard")

    body = response.json()
    assert response.status_code == 200
    assert [c["item_id"] for c in body["candidates"]] == ["item_complete"]
    assert body["metrics"]["in_progress_count"] == 1


# ---------------------------------------------------------------------------
# Urgency legend
# ---------------------------------------------------------------------------


def test_urgency_legend_has_the_exact_expected_labels_and_thresholds(
    api_app, sign_in, serve_repository
):
    sign_in("acct_test")
    serve_repository(StubRepository([]))

    response = TestClient(api_app).get("/v1/dashboard")

    legend = {entry["level"]: entry for entry in response.json()["urgency_legend"]}
    assert legend["expired"]["label"] == "Deadline passed"
    assert legend["critical"]["label"] == "Act now"
    assert legend["soon"]["label"] == "Closing soon"
    assert legend["later"]["label"] == "More time"
    assert legend["unknown"]["label"] == "Deadline unknown"
    assert legend["critical"] == {
        "level": "critical",
        "label": "Act now",
        "min_days": 0,
        "max_days": 2,
    }
    assert legend["soon"] == {
        "level": "soon",
        "label": "Closing soon",
        "min_days": 3,
        "max_days": 7,
    }


# ---------------------------------------------------------------------------
# Authentication and mounting
# ---------------------------------------------------------------------------


def test_is_unauthenticated_without_a_principal(api_app):
    response = TestClient(api_app).get("/v1/dashboard")

    assert response.status_code == 401
    assert response.json()["reason"] == "unauthenticated"


def test_the_production_app_mounts_the_dashboard_route():
    assert "/v1/dashboard" in production_app.openapi()["paths"]


def test_the_router_can_be_mounted_on_any_app_without_further_wiring(api_app):
    fresh = FastAPI()
    fresh.include_router(api_router)

    assert "/v1/dashboard" in fresh.openapi()["paths"]
