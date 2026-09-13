"""Tests for ``GET /v1/items/{item_id}``.

The route composes four account-scoped reads into one derived response. The property
under the heaviest test here is the one this route exists to protect: a request for an
item that belongs to a different account and a request for an item id that was never
stored come back byte-for-byte identical, because ``ScopedRepository.get_order_item``
answers both through the same composite-key lookup and the same ``None`` return, and the
handler raises the same error from that single result with no further lookup either way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple, Self

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.api import errors as errors_module
from app.api.auth import AccountScope, get_account_scope
from app.api.errors import install_error_handling
from app.db.base import Base
from app.db.models import (
    AccountRow,
    OrderItemRow,
    OrderRow,
    PolicyRuleRow,
    ReturnPolicyRow,
    ReturnSummaryRow,
)
from app.db.session import build_session_factory
from app.main import app as production_app
from app.models import (
    FactOrigin,
    HandoffEvidence,
    PolicyEligibility,
    ReturnState,
    ReturnSummaryUpdateSource,
)
from app.routes import api_router

TIMESTAMP = datetime(2026, 9, 8, 16, 30, tzinfo=UTC)


def _order_row(
    *,
    order_id: str = "order_1",
    account_id: str = "acct_test",
    retailer_order_reference: str | None = "REF-1",
    ordered_on: date | None = date(2026, 9, 1),
) -> OrderRow:
    return OrderRow(
        id=order_id,
        account_id=account_id,
        retailer_key="acme",
        retailer_name="Acme",
        retailer_order_reference=retailer_order_reference,
        ordered_on=ordered_on,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


@dataclass(frozen=True, kw_only=True)
class ItemSpec:
    """The overridable fields of a canned :class:`OrderItemRow`, grouped to keep
    ``_item_row`` itself down to a single parameter."""

    account_id: str = "acct_test"
    item_id: str = "item_1"
    order_id: str = "order_1"
    variant: str | None = "Black"
    price_amount_minor: int | None = 2500
    price_currency: str | None = "USD"
    delivered_on: date | None = date(2026, 9, 5)


def _item_row(spec: ItemSpec | None = None) -> OrderItemRow:
    spec = spec if spec is not None else ItemSpec()
    return OrderItemRow(
        account_id=spec.account_id,
        id=spec.item_id,
        order_id=spec.order_id,
        description="Wireless Mouse",
        variant=spec.variant,
        quantity=1,
        price_amount_minor=spec.price_amount_minor,
        price_currency=spec.price_currency,
        delivered_on=spec.delivered_on,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


@dataclass(frozen=True, kw_only=True)
class PolicySpec:
    """The overridable fields of a canned :class:`ReturnPolicyRow`, grouped to keep
    ``_policy_row`` itself down to a couple of parameters."""

    account_id: str = "acct_test"
    item_id: str = "item_1"
    eligibility: PolicyEligibility = PolicyEligibility.ELIGIBLE
    return_by_value: date | None = date(2026, 9, 20)
    return_by_origin: FactOrigin | None = FactOrigin.RETAILER_STATED
    return_by_confidence: float | None = 0.9
    fee_amount_minor: int | None = 0
    fee_currency: str | None = "USD"
    fee_origin: FactOrigin | None = FactOrigin.RETAILER_STATED
    fee_confidence: float | None = 1.0


def _policy_row(
    spec: PolicySpec | None = None, *, rules: list[PolicyRuleRow] | None = None
) -> ReturnPolicyRow:
    spec = spec if spec is not None else PolicySpec()
    policy = ReturnPolicyRow(
        account_id=spec.account_id,
        item_id=spec.item_id,
        eligibility=spec.eligibility,
        return_by_value=spec.return_by_value,
        return_by_origin=spec.return_by_origin,
        return_by_confidence=spec.return_by_confidence,
        fee_amount_minor=spec.fee_amount_minor,
        fee_currency=spec.fee_currency,
        fee_origin=spec.fee_origin,
        fee_confidence=spec.fee_confidence,
        version=1,
        updated_at=TIMESTAMP,
    )
    policy.rules = rules if rules is not None else []
    return policy


def _summary_row(
    *,
    account_id: str = "acct_test",
    item_id: str = "item_1",
    state: ReturnState = ReturnState.NOT_STARTED,
    update_source: ReturnSummaryUpdateSource = ReturnSummaryUpdateSource.SYSTEM_INITIALIZATION,
    handoff_evidence: HandoffEvidence | None = None,
) -> ReturnSummaryRow:
    return ReturnSummaryRow(
        account_id=account_id,
        item_id=item_id,
        state=state,
        update_source=update_source,
        handoff_evidence=handoff_evidence,
        observed_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


class StubRepository:
    """Answers exactly the four reads ``read_item`` calls, from canned rows."""

    def __init__(
        self,
        *,
        item: OrderItemRow | None,
        order: OrderRow | None = None,
        policy: ReturnPolicyRow | None = None,
        summary: ReturnSummaryRow | None = None,
    ) -> None:
        self._item = item
        self._order = order
        self._policy = policy
        self._summary = summary

    async def get_order_item(self, item_id: str) -> OrderItemRow | None:
        return self._item

    async def get_order(self, order_id: str) -> OrderRow | None:
        return self._order

    async def get_return_policy(self, item_id: str) -> ReturnPolicyRow | None:
        return self._policy

    async def get_return_summary(self, item_id: str) -> ReturnSummaryRow | None:
        return self._summary


class _ItemOnlySession:
    """Answers only ``OrderItemRow`` composite-key lookups.

    Mirrors the real table's ``(account_id, id)`` primary key exactly: a row is found
    only when both parts of the identity tuple match. This is what lets the byte-identical
    test below exercise the real ``ScopedRepository.get_order_item`` composite-key lookup
    rather than a hand-rolled stand-in for its account-scoping behavior.
    """

    def __init__(self, rows: dict[tuple[str, str], OrderItemRow]) -> None:
        self._rows = rows
        self.closed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc_info: object) -> bool:
        self.closed = True
        return False

    async def get(self, entity: type, identity: object, **_kwargs: object) -> OrderItemRow | None:
        if entity is OrderItemRow and isinstance(identity, tuple):
            return self._rows.get(identity)
        return None


class _ItemOnlySessionFactory:
    """Stands in for the session factory the lifespan installs on ``app.state``."""

    def __init__(self, rows: dict[tuple[str, str], OrderItemRow]) -> None:
        self._rows = rows
        self.sessions: list[_ItemOnlySession] = []

    def __call__(self) -> _ItemOnlySession:
        session = _ItemOnlySession(self._rows)
        self.sessions.append(session)
        return session


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


def test_read_item_returns_full_candidate_detail(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    rule = PolicyRuleRow(
        account_id="acct_test",
        item_id="item_1",
        id="rule_1",
        text="Unopened items only.",
        origin=FactOrigin.RETAILER_STATED,
        confidence=0.8,
    )
    serve_repository(
        StubRepository(
            item=_item_row(),
            order=_order_row(),
            policy=_policy_row(rules=[rule]),
            summary=_summary_row(),
        )
    )

    response = TestClient(api_app).get("/v1/items/item_1")

    assert response.status_code == 200
    body = response.json()
    assert "generated_at" in body
    candidate = body["candidate"]
    assert candidate["item_id"] == "item_1"
    assert candidate["order_id"] == "order_1"
    assert candidate["retailer"] == {"key": "acme", "name": "Acme"}
    assert candidate["order_reference"] == "REF-1"
    assert candidate["item"] == {
        "description": "Wireless Mouse",
        "variant": "Black",
        "quantity": 1,
        "price": {"amount_minor": 2500, "currency": "USD"},
    }
    assert candidate["dates"] == {
        "ordered_on": "2026-09-01",
        "delivered_on": "2026-09-05",
        "return_by": {"value": "2026-09-20", "origin": "retailer_stated", "confidence": 0.9},
    }
    assert candidate["policy"] == {
        "eligibility": "eligible",
        "fee": {
            "value": {"amount_minor": 0, "currency": "USD"},
            "origin": "retailer_stated",
            "confidence": 1.0,
        },
        "rules": [
            {
                "id": "rule_1",
                "text": "Unopened items only.",
                "origin": "retailer_stated",
                "confidence": 0.8,
            }
        ],
    }
    assert candidate["return_summary"]["state"] == "not_started"


def test_nullable_fields_are_allowed_to_be_null(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(
        StubRepository(
            item=_item_row(
                ItemSpec(
                    variant=None,
                    price_amount_minor=None,
                    price_currency=None,
                    delivered_on=None,
                )
            ),
            order=_order_row(retailer_order_reference=None, ordered_on=None),
            policy=_policy_row(
                PolicySpec(
                    return_by_value=None,
                    return_by_origin=None,
                    return_by_confidence=None,
                    fee_amount_minor=None,
                    fee_currency=None,
                    fee_origin=None,
                    fee_confidence=None,
                ),
                rules=[],
            ),
            summary=_summary_row(),
        )
    )

    response = TestClient(api_app).get("/v1/items/item_1")

    assert response.status_code == 200
    candidate = response.json()["candidate"]
    assert candidate["item"]["variant"] is None
    assert candidate["item"]["price"] is None
    assert candidate["dates"]["delivered_on"] is None
    assert candidate["dates"]["ordered_on"] is None
    assert candidate["dates"]["return_by"] is None
    assert candidate["order_reference"] is None
    assert candidate["policy"]["fee"] is None
    assert candidate["policy"]["rules"] == []


class _NextActionCase(NamedTuple):
    state: ReturnState
    eligibility: PolicyEligibility
    return_by_offset_days: int
    expected_code: str


@pytest.mark.parametrize(
    "case",
    [
        _NextActionCase(
            ReturnState.QR_READY, PolicyEligibility.ELIGIBLE, 10, "open_retailer_result"
        ),
        _NextActionCase(
            ReturnState.LABEL_READY, PolicyEligibility.ELIGIBLE, 10, "open_retailer_result"
        ),
        _NextActionCase(
            ReturnState.IN_PROGRESS, PolicyEligibility.ELIGIBLE, 10, "focus_active_return"
        ),
        _NextActionCase(
            ReturnState.NOT_STARTED, PolicyEligibility.INELIGIBLE, 10, "manual_required"
        ),
        _NextActionCase(ReturnState.NOT_STARTED, PolicyEligibility.ELIGIBLE, -1, "manual_required"),
        _NextActionCase(ReturnState.NOT_STARTED, PolicyEligibility.ELIGIBLE, 10, "start_return"),
        _NextActionCase(ReturnState.HANDED_TO_CARRIER, PolicyEligibility.ELIGIBLE, 10, "none"),
        _NextActionCase(ReturnState.COMPLETE, PolicyEligibility.ELIGIBLE, 10, "none"),
    ],
)
def test_next_action_follows_the_precedence_table(api_app, sign_in, serve_repository, case):
    sign_in("acct_test")
    today = datetime.now(UTC).date()
    handoff_evidence = (
        HandoffEvidence.USER_CONFIRMED if case.state is ReturnState.HANDED_TO_CARRIER else None
    )
    serve_repository(
        StubRepository(
            item=_item_row(),
            order=_order_row(),
            policy=_policy_row(
                PolicySpec(
                    eligibility=case.eligibility,
                    return_by_value=today + timedelta(days=case.return_by_offset_days),
                )
            ),
            summary=_summary_row(state=case.state, handoff_evidence=handoff_evidence),
        )
    )

    response = TestClient(api_app).get("/v1/items/item_1")

    assert response.json()["candidate"]["next_action"]["code"] == case.expected_code


@pytest.mark.parametrize(
    ("return_by_offset_days", "expected_level"),
    [
        (-1, "expired"),
        (0, "critical"),
        (2, "critical"),
        (3, "soon"),
        (7, "soon"),
        (8, "later"),
    ],
)
def test_urgency_level_follows_the_day_thresholds(
    api_app, sign_in, serve_repository, return_by_offset_days, expected_level
):
    sign_in("acct_test")
    today = datetime.now(UTC).date()
    serve_repository(
        StubRepository(
            item=_item_row(),
            order=_order_row(),
            policy=_policy_row(
                PolicySpec(return_by_value=today + timedelta(days=return_by_offset_days))
            ),
            summary=_summary_row(),
        )
    )

    response = TestClient(api_app).get("/v1/items/item_1")

    urgency = response.json()["candidate"]["urgency"]
    assert urgency["level"] == expected_level
    assert urgency["days_remaining"] == return_by_offset_days


def test_urgency_is_unknown_when_return_by_is_absent(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(
        StubRepository(
            item=_item_row(),
            order=_order_row(),
            policy=_policy_row(
                PolicySpec(return_by_value=None, return_by_origin=None, return_by_confidence=None)
            ),
            summary=_summary_row(),
        )
    )

    response = TestClient(api_app).get("/v1/items/item_1")

    candidate = response.json()["candidate"]
    assert candidate["urgency"] == {"level": "unknown", "days_remaining": None}
    assert candidate["dates"]["return_by"] is None


def test_is_not_found_when_the_item_is_absent(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(StubRepository(item=None))

    response = TestClient(api_app).get("/v1/items/item_missing")

    assert response.status_code == 404
    assert response.json()["reason"] == "not_found"


def test_is_not_found_when_the_items_order_is_missing(api_app, sign_in, serve_repository):
    # Every stored item belongs to a stored order by construction; reaching this would
    # mean that invariant broke, not that the caller did anything wrong. Treated the same
    # as a genuine miss regardless.
    sign_in("acct_test")
    serve_repository(StubRepository(item=_item_row(), order=None))

    response = TestClient(api_app).get("/v1/items/item_1")

    assert response.status_code == 404
    assert response.json()["reason"] == "not_found"


def test_is_not_found_when_the_items_policy_is_missing(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(StubRepository(item=_item_row(), order=_order_row(), policy=None))

    response = TestClient(api_app).get("/v1/items/item_1")

    assert response.status_code == 404
    assert response.json()["reason"] == "not_found"


def test_is_not_found_when_the_items_summary_is_missing(api_app, sign_in, serve_repository):
    sign_in("acct_test")
    serve_repository(
        StubRepository(item=_item_row(), order=_order_row(), policy=_policy_row(), summary=None)
    )

    response = TestClient(api_app).get("/v1/items/item_1")

    assert response.status_code == 404
    assert response.json()["reason"] == "not_found"


# ---------------------------------------------------------------------------
# Cross-account access must be indistinguishable from a genuinely missing item
# ---------------------------------------------------------------------------


def test_cross_account_item_and_missing_item_are_byte_identical(api_app, sign_in, monkeypatch):
    # The exact leakage this route exists to prevent: a client that guesses or otherwise
    # obtains another account's item id must learn nothing that a made-up id would not
    # also reveal. This goes through the real dependency chain and the real
    # ScopedRepository.get_order_item composite-key lookup, not a hand-simulated stand-in
    # for it - only the item's account/id pair is ever stored, exactly as the real
    # composite primary key would store it.
    sign_in("acct_a")
    owned_by_b = _item_row(ItemSpec(account_id="acct_b", item_id="item_owned_by_b"))
    api_app.state.session_factory = _ItemOnlySessionFactory(
        {("acct_b", "item_owned_by_b"): owned_by_b}
    )
    monkeypatch.setattr(errors_module, "_new_request_id", lambda: "req_fixed_for_test")

    client = TestClient(api_app)
    cross_account_response = client.get("/v1/items/item_owned_by_b")
    never_existed_response = client.get("/v1/items/item_never_existed")

    assert cross_account_response.status_code == never_existed_response.status_code == 404
    assert (
        cross_account_response.headers["content-type"]
        == never_existed_response.headers["content-type"]
    )
    assert cross_account_response.content == never_existed_response.content


# ---------------------------------------------------------------------------
# Account scope comes from the principal and from nowhere else
# ---------------------------------------------------------------------------


def test_is_unauthenticated_without_a_principal(api_app):
    response = TestClient(api_app).get("/v1/items/item_1")

    assert response.status_code == 401
    assert response.json()["reason"] == "unauthenticated"


def test_never_opens_a_session_for_an_unauthenticated_request(api_app):
    factory = _ItemOnlySessionFactory({})
    api_app.state.session_factory = factory

    response = TestClient(api_app).get("/v1/items/item_1")

    assert response.status_code == 401
    assert factory.sessions == []


def test_ignores_an_account_id_supplied_by_the_client(api_app, sign_in, serve_repository):
    # Query string, header and cookie all carry an attacker-chosen account id; the item
    # route accepts no account id at all from the client, and the reply must still be
    # scoped only to the signed-in account.
    sign_in("acct_known")
    serve_repository(
        StubRepository(
            item=_item_row(ItemSpec(account_id="acct_known")),
            order=_order_row(account_id="acct_known"),
            policy=_policy_row(PolicySpec(account_id="acct_known")),
            summary=_summary_row(account_id="acct_known"),
        )
    )

    client = TestClient(api_app)
    client.cookies.set("account_id", "acct_attacker")
    response = client.get(
        "/v1/items/item_1",
        params={"account_id": "acct_attacker"},
        headers={"X-Account-Id": "acct_attacker"},
    )

    assert response.status_code == 200
    assert "acct_attacker" not in response.text


# ---------------------------------------------------------------------------
# Mounting
# ---------------------------------------------------------------------------


def test_the_production_app_mounts_the_item_route():
    assert "/v1/items/{item_id}" in production_app.openapi()["paths"]


def test_the_router_can_be_mounted_on_any_app_without_further_wiring(api_app):
    fresh = FastAPI()
    fresh.include_router(api_router)

    assert "/v1/items/{item_id}" in fresh.openapi()["paths"]


# ---------------------------------------------------------------------------
# The same chain against real PostgreSQL
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_the_chain_hides_a_foreign_item_from_postgresql(database_engine, monkeypatch):
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add(
            AccountRow(
                id="acct_integration",
                google_subject="google-subject-1",
                email=None,
                display_name=None,
                avatar_url=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        session.add(
            AccountRow(
                id="acct_other",
                google_subject="google-subject-2",
                email=None,
                display_name=None,
                avatar_url=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        session.add(_order_row(account_id="acct_integration"))
        session.add(_order_row(order_id="order_other", account_id="acct_other"))
        session.add(_item_row(ItemSpec(account_id="acct_integration")))
        session.add(
            _item_row(
                ItemSpec(account_id="acct_other", item_id="item_other", order_id="order_other")
            )
        )
        session.add(_policy_row(PolicySpec(account_id="acct_integration")))
        session.add(_policy_row(PolicySpec(account_id="acct_other", item_id="item_other")))
        session.add(_summary_row(account_id="acct_integration"))
        session.add(_summary_row(account_id="acct_other", item_id="item_other"))
        await session.commit()

    monkeypatch.setattr(errors_module, "_new_request_id", lambda: "req_fixed_for_test")

    app = FastAPI()
    install_error_handling(app)
    app.include_router(api_router)
    app.state.session_factory = session_factory
    app.dependency_overrides[get_account_scope] = lambda: AccountScope(
        account_id="acct_integration"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        own_response = await client.get("/v1/items/item_1")
        foreign_response = await client.get("/v1/items/item_other")
        missing_response = await client.get("/v1/items/item_never_existed")

    assert own_response.status_code == 200
    assert own_response.json()["candidate"]["item_id"] == "item_1"
    assert foreign_response.status_code == missing_response.status_code == 404
    assert foreign_response.content == missing_response.content
