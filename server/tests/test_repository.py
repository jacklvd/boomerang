"""Tests for the account-scoped repository boundary.

Two kinds of test live here. The first kind runs without Docker: it drives
:class:`~app.db.repository.ScopedRepository` against a fake session double to prove, line
by line, that every method builds an account-scoped query - fast, and part of the
Docker-free coverage floor. The second kind is marked ``integration`` and runs against a
real, disposable PostgreSQL database: it seeds two real accounts with real rows and
proves the actual cross-account read returns nothing, because a stubbed session cannot
demonstrate that a foreign account's row genuinely is not visible - only a real database
with real data can.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError

from app.db.base import Base
from app.db.models import (
    ORM_ROWS,
    UNSCOPED_ROWS,
    AccountRow,
    OrderItemRow,
    OrderRow,
    PolicyRuleRow,
    PreferenceSetRow,
    PreferenceValueRow,
    ReturnPolicyRow,
    ReturnSummaryRow,
)
from app.db.repository import (
    ACCOUNT_COLUMN,
    ReturnSummaryCasOutcome,
    ScopedRepository,
    unscoped_rows,
)
from app.db.session import build_session_factory
from app.models import (
    FactOrigin,
    PolicyEligibility,
    Preference,
    ReturnState,
    ReturnSummaryUpdateSource,
)

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

TIMESTAMP = datetime(2026, 9, 8, 16, 30, tzinfo=UTC)


class _FakeScalarResult:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        return self._values

    def one_or_none(self) -> Any:
        return self._values[0] if self._values else None


class _FakeExecuteResult:
    """A minimal stand-in for the Result of an ``UPDATE ... RETURNING`` execute."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeSession:
    """A minimal stand-in for AsyncSession that records how it was called."""

    def __init__(
        self,
        *,
        get_result: Any = None,
        scalars_result: list[Any] | None = None,
        execute_results: list[Any] | None = None,
        execute_error: Exception | None = None,
    ) -> None:
        self.get_calls: list[tuple[Any, Any, dict[str, Any]]] = []
        self.scalars_calls: list[Select[Any]] = []
        self.execute_calls: list[tuple[Any, Any]] = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self._get_result = get_result
        self._scalars_result = scalars_result or []
        self._execute_results = list(execute_results or [])
        self._execute_error = execute_error

    async def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
        self.get_calls.append((entity, ident, kwargs))
        return self._get_result

    async def scalars(self, statement: Select[Any]) -> _FakeScalarResult:
        self.scalars_calls.append(statement)
        return _FakeScalarResult(self._scalars_result)

    async def execute(self, statement: Any, parameters: Any = None) -> _FakeExecuteResult:
        self.execute_calls.append((statement, parameters))
        if self._execute_error is not None:
            raise self._execute_error
        if self._execute_results:
            return _FakeExecuteResult(self._execute_results.pop(0))
        return _FakeExecuteResult(None)

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


def _fake_repository(
    *,
    get_result: Any = None,
    scalars_result: list[Any] | None = None,
    execute_results: list[Any] | None = None,
    execute_error: Exception | None = None,
) -> tuple[ScopedRepository, _FakeSession]:
    fake_session = _FakeSession(
        get_result=get_result,
        scalars_result=scalars_result,
        execute_results=execute_results,
        execute_error=execute_error,
    )
    repository = ScopedRepository(cast("AsyncSession", fake_session), "account-a")
    return repository, fake_session


# ---------------------------------------------------------------------------
# unscoped_rows / ACCOUNT_COLUMN: pure-function exhaustiveness check.
# ---------------------------------------------------------------------------


def test_account_column_registers_every_row_not_declared_unscoped():
    assert set(ACCOUNT_COLUMN) == set(ORM_ROWS) - UNSCOPED_ROWS


def test_unscoped_rows_is_empty_against_the_real_registry():
    assert unscoped_rows(ACCOUNT_COLUMN) == frozenset()


def test_unscoped_rows_reports_a_row_dropped_from_the_registry():
    incomplete_registry = dict(ACCOUNT_COLUMN)
    del incomplete_registry[OrderItemRow]
    assert unscoped_rows(incomplete_registry) == frozenset({OrderItemRow})


def test_unscoped_rows_never_reports_a_row_declared_unscoped():
    # A row declared in UNSCOPED_ROWS (AccountRow is its own scope, PairingRequestRow
    # cannot be bound to an account before approval) legitimately carries no
    # account_id - so an empty registry must still exclude every one of them from
    # the report, not just AccountRow.
    assert unscoped_rows({}) == frozenset(ORM_ROWS) - UNSCOPED_ROWS


# ---------------------------------------------------------------------------
# ScopedRepository: every method scopes its query by the constructed account id.
# ---------------------------------------------------------------------------


async def test_get_account_looks_up_its_own_constructed_id():
    repository, fake_session = _fake_repository()
    await repository.get_account()
    assert fake_session.get_calls == [(AccountRow, "account-a", {})]


async def test_get_order_filters_by_account_id_and_order_id():
    # orders.id is a single-column primary key (the section 5.1 invariant), so get_order
    # cannot use session.get() with a composite identity tuple - it must filter explicitly.
    order = OrderRow(
        id="order-1",
        account_id="account-a",
        retailer_key="example-retailer",
        retailer_name="Example Retailer",
        retailer_order_reference=None,
        ordered_on=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    repository, fake_session = _fake_repository(scalars_result=[order])
    result = await repository.get_order("order-1")
    assert result is order
    assert len(fake_session.scalars_calls) == 1
    compiled = str(fake_session.scalars_calls[0].compile())
    assert "orders.id" in compiled
    assert "orders.account_id" in compiled


async def test_get_order_item_scopes_identity_by_account_then_item_id():
    repository, fake_session = _fake_repository()
    await repository.get_order_item("item-1")
    assert fake_session.get_calls == [(OrderItemRow, ("account-a", "item-1"), {})]


async def test_get_return_policy_scopes_identity_and_eager_loads_rules():
    repository, fake_session = _fake_repository()
    await repository.get_return_policy("item-1")
    assert len(fake_session.get_calls) == 1
    entity, ident, kwargs = fake_session.get_calls[0]
    assert entity is ReturnPolicyRow
    assert ident == ("account-a", "item-1")
    assert kwargs["options"]  # selectinload(ReturnPolicyRow.rules) - lazy="raise" needs this


async def test_get_return_summary_scopes_identity_by_account_then_item_id():
    repository, fake_session = _fake_repository()
    await repository.get_return_summary("item-1")
    assert fake_session.get_calls == [(ReturnSummaryRow, ("account-a", "item-1"), {})]


async def test_get_preference_set_scopes_identity_and_eager_loads_values():
    repository, fake_session = _fake_repository()
    await repository.get_preference_set()
    assert len(fake_session.get_calls) == 1
    entity, ident, kwargs = fake_session.get_calls[0]
    assert entity is PreferenceSetRow
    assert ident == "account-a"
    assert kwargs["options"]  # selectinload(PreferenceSetRow.values) - lazy="raise" needs this


async def test_list_orders_filters_the_query_by_account_id():
    repository, fake_session = _fake_repository(scalars_result=[])
    result = await repository.list_orders()
    assert result == []
    assert len(fake_session.scalars_calls) == 1
    compiled = str(fake_session.scalars_calls[0].compile())
    assert "orders.account_id" in compiled


async def test_list_order_items_filters_the_query_by_account_id():
    repository, fake_session = _fake_repository(scalars_result=[])
    result = await repository.list_order_items()
    assert result == []
    assert len(fake_session.scalars_calls) == 1
    compiled = str(fake_session.scalars_calls[0].compile())
    assert "order_items.account_id" in compiled


async def test_list_order_items_eager_loads_order_policy_rules_and_summary():
    # A dashboard-shaped read must never trip lazy="raise" - proven here by asserting
    # every relationship the dashboard walks was attached as a loader option, and
    # proven for real (rather than just "an option was attached") by the integration
    # test below, which actually walks these attributes off a freshly queried row.
    repository, fake_session = _fake_repository(scalars_result=[])
    await repository.list_order_items()
    statement = fake_session.scalars_calls[0]
    loaded_paths = [
        str(option.path)
        for option in statement._with_options  # noqa: SLF001 - no public introspection API exists
        if hasattr(option, "path")
    ]
    assert any("OrderItemRow.order ->" in path for path in loaded_paths)
    assert any("OrderItemRow.return_policy ->" in path and "rules" in path for path in loaded_paths)
    assert any("OrderItemRow.return_summary ->" in path for path in loaded_paths)


async def test_replace_preference_set_rejects_duplicate_values():
    repository, _fake_session = _fake_repository()
    with pytest.raises(ValidationError):
        await repository.replace_preference_set(
            [Preference.LOWEST_COST, Preference.LOWEST_COST],
            TIMESTAMP,
        )


async def test_replace_preference_set_upserts_scoped_by_account_then_commits():
    repository, fake_session = _fake_repository()
    result = await repository.replace_preference_set(
        [Preference.LOWEST_COST, Preference.NO_PRINTER],
        TIMESTAMP,
    )

    assert isinstance(result, PreferenceSetRow)
    assert {value.value for value in result.values} == {
        Preference.LOWEST_COST,
        Preference.NO_PRINTER,
    }

    assert len(fake_session.execute_calls) == 3
    upsert_statement, delete_statement, insert_statement = (
        call[0] for call in fake_session.execute_calls
    )
    assert "preference_sets" in str(upsert_statement.compile())
    assert "ON CONFLICT" in str(upsert_statement.compile())
    assert "preference_values.account_id" in str(delete_statement.compile())
    assert "preference_values" in str(insert_statement.compile())
    insert_parameters = fake_session.execute_calls[2][1]
    assert insert_parameters == [
        {"account_id": "account-a", "value": Preference.LOWEST_COST},
        {"account_id": "account-a", "value": Preference.NO_PRINTER},
    ]
    assert fake_session.commit_calls == 1


async def test_replace_preference_set_skips_the_bulk_insert_when_values_is_empty():
    repository, fake_session = _fake_repository()
    result = await repository.replace_preference_set([], TIMESTAMP)

    assert result.values == []
    # Only the parent upsert and the wipe of old values - no insert statement at all,
    # since there is nothing to insert.
    assert len(fake_session.execute_calls) == 2
    assert fake_session.commit_calls == 1


async def test_reset_return_summary_if_abandoned_scopes_the_conditional_update():
    repository, fake_session = _fake_repository(execute_results=[None], get_result=None)
    result = await repository.reset_return_summary_if_abandoned(
        "item-1",
        observed_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )

    assert result.outcome is ReturnSummaryCasOutcome.NOT_FOUND
    assert result.row is None
    assert len(fake_session.execute_calls) == 1
    compiled = str(fake_session.execute_calls[0][0].compile())
    assert "return_summaries.account_id" in compiled
    assert "return_summaries.item_id" in compiled
    assert "handoff_evidence" in compiled
    assert "observed_at" in compiled
    # The lookup that classifies a refusal from a genuine absence is itself scoped.
    assert fake_session.get_calls == [(ReturnSummaryRow, ("account-a", "item-1"), {})]


async def test_reset_return_summary_if_abandoned_applies_when_the_update_returns_a_row():
    updated_row = ReturnSummaryRow(
        account_id="account-a",
        item_id="item-1",
        state=ReturnState.NOT_STARTED,
        update_source=ReturnSummaryUpdateSource.USER_CONFIRMED,
        handoff_evidence=None,
        observed_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    repository, fake_session = _fake_repository(execute_results=[updated_row])

    result = await repository.reset_return_summary_if_abandoned(
        "item-1",
        observed_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )

    assert result.outcome is ReturnSummaryCasOutcome.APPLIED
    assert result.row is updated_row
    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 0
    # An applied write never needs the classifying lookup - it already has its row.
    assert fake_session.get_calls == []


async def test_reset_return_summary_if_abandoned_refuses_when_a_stored_row_does_not_match():
    stored_row = ReturnSummaryRow(
        account_id="account-a",
        item_id="item-1",
        state=ReturnState.QR_READY,
        update_source=ReturnSummaryUpdateSource.EXTENSION_LIVE_PAGE,
        handoff_evidence=None,
        observed_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    repository, fake_session = _fake_repository(execute_results=[None], get_result=stored_row)

    result = await repository.reset_return_summary_if_abandoned(
        "item-1",
        observed_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )

    assert result.outcome is ReturnSummaryCasOutcome.REFUSED
    assert result.row is stored_row
    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 0


async def test_reset_return_summary_if_abandoned_treats_a_serialization_failure_as_a_lost_race():
    stored_row = ReturnSummaryRow(
        account_id="account-a",
        item_id="item-1",
        state=ReturnState.IN_PROGRESS,
        update_source=ReturnSummaryUpdateSource.EXTENSION_LIVE_PAGE,
        handoff_evidence=None,
        observed_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )

    class _FakeSerializationOrigError(Exception):
        sqlstate = "40001"

    error = DBAPIError("statement", {}, _FakeSerializationOrigError())
    repository, fake_session = _fake_repository(execute_error=error, get_result=stored_row)

    result = await repository.reset_return_summary_if_abandoned(
        "item-1",
        observed_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )

    # Lost the race, exactly as a plain zero-rows-affected refusal would - and never
    # retried: only one execute call was ever made.
    assert result.outcome is ReturnSummaryCasOutcome.REFUSED
    assert result.row is stored_row
    assert len(fake_session.execute_calls) == 1
    assert fake_session.rollback_calls == 1
    assert fake_session.commit_calls == 0


async def test_reset_return_summary_if_abandoned_reraises_a_non_serialization_dbapi_error():
    class _FakeOtherOrigError(Exception):
        sqlstate = "23505"

    error = DBAPIError("statement", {}, _FakeOtherOrigError())
    repository, fake_session = _fake_repository(execute_error=error)

    with pytest.raises(DBAPIError):
        await repository.reset_return_summary_if_abandoned(
            "item-1",
            observed_at=TIMESTAMP,
            updated_at=TIMESTAMP,
        )

    assert fake_session.rollback_calls == 0
    assert fake_session.commit_calls == 0


# ---------------------------------------------------------------------------
# Genuine cross-account behaviour: requires a real database with real rows.
# ---------------------------------------------------------------------------


def _account_row(account_id: str) -> AccountRow:
    return AccountRow(
        id=account_id,
        google_subject=f"google-{account_id}",
        email=None,
        display_name=None,
        avatar_url=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _order_row(account_id: str, order_id: str) -> OrderRow:
    # retailer_order_reference is set (not None) so that seeding more than one order per
    # account here never collides with uq_orders_retailer_reference's NULLS NOT DISTINCT
    # constraint - that collision is exercised deliberately in test_db_integration.py.
    return OrderRow(
        id=order_id,
        account_id=account_id,
        retailer_key="example-retailer",
        retailer_name="Example Retailer",
        retailer_order_reference=f"reference-{order_id}",
        ordered_on=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


@pytest.mark.integration
async def test_scoped_repository_cannot_see_another_accounts_order(
    database_engine: AsyncEngine,
) -> None:
    """Cross-account reads must be indistinguishable from a genuinely absent id.

    Two real accounts are seeded with their own real orders. Account A's repository is
    then asked for account B's order id, and separately for an id that was never
    written at all. Both must come back None, through the same call, with nothing to
    tell them apart.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                _account_row("account-a"),
                _account_row("account-b"),
                _order_row("account-a", "order-owned-by-a"),
                _order_row("account-b", "order-owned-by-b"),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")

        own_order = await repository_a.get_order("order-owned-by-a")
        cross_account_order = await repository_a.get_order("order-owned-by-b")
        nonexistent_order = await repository_a.get_order("order-does-not-exist")

    assert own_order is not None
    assert own_order.id == "order-owned-by-a"
    assert cross_account_order is None
    assert nonexistent_order is None
    assert cross_account_order == nonexistent_order


@pytest.mark.integration
async def test_scoped_repository_list_orders_never_includes_another_account(
    database_engine: AsyncEngine,
) -> None:
    """list_orders proves the same property over a collection, not just a single get."""
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                _account_row("account-a"),
                _account_row("account-b"),
                _order_row("account-a", "order-a-1"),
                _order_row("account-a", "order-a-2"),
                _order_row("account-b", "order-b-1"),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")
        orders = await repository_a.list_orders()

    assert {order.id for order in orders} == {"order-a-1", "order-a-2"}


def _order_item_row(account_id: str, order_id: str, item_id: str) -> OrderItemRow:
    return OrderItemRow(
        account_id=account_id,
        id=item_id,
        order_id=order_id,
        description="A stored item",
        variant=None,
        quantity=1,
        price_amount_minor=None,
        price_currency=None,
        delivered_on=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _return_policy_row(account_id: str, item_id: str) -> ReturnPolicyRow:
    row = ReturnPolicyRow(
        account_id=account_id,
        item_id=item_id,
        eligibility=PolicyEligibility.ELIGIBLE,
        return_by_value=None,
        return_by_origin=None,
        return_by_confidence=None,
        fee_amount_minor=None,
        fee_currency=None,
        fee_origin=None,
        fee_confidence=None,
        version=1,
        updated_at=TIMESTAMP,
    )
    row.rules = [
        PolicyRuleRow(
            account_id=account_id,
            item_id=item_id,
            id=f"rule-{item_id}",
            text="Returns accepted within 30 days.",
            origin=FactOrigin.RETAILER_STATED,
            confidence=None,
        ),
    ]
    return row


def _return_summary_row(
    account_id: str,
    item_id: str,
    *,
    state: ReturnState = ReturnState.IN_PROGRESS,
    observed_at: datetime = TIMESTAMP,
) -> ReturnSummaryRow:
    return ReturnSummaryRow(
        account_id=account_id,
        item_id=item_id,
        state=state,
        update_source=ReturnSummaryUpdateSource.EXTENSION_LIVE_PAGE,
        handoff_evidence=None,
        observed_at=observed_at,
        updated_at=observed_at,
    )


@pytest.mark.integration
async def test_list_order_items_never_includes_another_accounts_item_and_loads_eagerly(
    database_engine: AsyncEngine,
) -> None:
    """The dashboard-shaped read is both account-scoped and safe to walk without lazy loads."""
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                _account_row("account-a"),
                _account_row("account-b"),
                _order_row("account-a", "order-a-1"),
                _order_row("account-b", "order-b-1"),
                _order_item_row("account-a", "order-a-1", "item-a-1"),
                _order_item_row("account-b", "order-b-1", "item-b-1"),
                _return_policy_row("account-a", "item-a-1"),
                _return_summary_row("account-a", "item-a-1"),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")
        items = await repository_a.list_order_items()

        assert {item.id for item in items} == {"item-a-1"}
        (item,) = items
        # Touching every eager-loaded relationship here, still inside the session that
        # ran the query, is what actually proves lazy="raise" never fires - a mapper
        # configured without the right selectinload would raise InvalidRequestError
        # the moment any of these attributes were touched, not before.
        assert item.order.id == "order-a-1"
        assert item.return_policy is not None
        assert [rule.id for rule in item.return_policy.rules] == ["rule-item-a-1"]
        assert item.return_summary is not None
        assert item.return_summary.state is ReturnState.IN_PROGRESS


@pytest.mark.integration
async def test_scoped_repository_get_order_item_cannot_see_another_accounts_item(
    database_engine: AsyncEngine,
) -> None:
    """``get_order_item`` itself must refuse a foreign item, called in isolation.

    This calls :meth:`ScopedRepository.get_order_item` directly - never through the
    ``/v1/items/{id}`` route, and never followed by ``get_order`` or any other method
    that route also calls. That chain has its own defensive checks (a mismatched order
    id raises the same not-found outcome), which is exactly what let a real regression
    here go undetected earlier: the route's own test kept passing because a *different*
    method's scoping caught the mismatch one step later. Calling this method alone,
    against real rows for two accounts, is the only way a regression in its own
    scoping can be caught by something other than luck.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                _account_row("account-a"),
                _account_row("account-b"),
                _order_row("account-a", "order-a-1"),
                _order_row("account-b", "order-b-1"),
                _order_item_row("account-a", "order-a-1", "item-a-1"),
                _order_item_row("account-b", "order-b-1", "item-b-1"),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")

        own_item = await repository_a.get_order_item("item-a-1")
        cross_account_item = await repository_a.get_order_item("item-b-1")
        nonexistent_item = await repository_a.get_order_item("item-does-not-exist")

    assert own_item is not None
    assert own_item.id == "item-a-1"
    assert cross_account_item is None
    assert nonexistent_item is None
    assert cross_account_item == nonexistent_item


@pytest.mark.integration
async def test_scoped_repository_get_return_policy_cannot_see_another_accounts_policy(
    database_engine: AsyncEngine,
) -> None:
    """``get_return_policy`` itself must refuse a foreign item's policy, in isolation.

    Order item ids are globally unique (``uq_order_items_id`` in ``app.db.models``), so
    once an item id is known to belong to this account, nothing else on the
    ``/v1/items/{id}`` chain would ever exercise this method with a wrong-account item
    id - there is no neighbouring method left to mask a regression here, which makes a
    direct test the only thing that can catch one.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                _account_row("account-a"),
                _account_row("account-b"),
                _order_row("account-a", "order-a-1"),
                _order_row("account-b", "order-b-1"),
                _order_item_row("account-a", "order-a-1", "item-a-1"),
                _order_item_row("account-b", "order-b-1", "item-b-1"),
                _return_policy_row("account-a", "item-a-1"),
                _return_policy_row("account-b", "item-b-1"),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")

        own_policy = await repository_a.get_return_policy("item-a-1")
        cross_account_policy = await repository_a.get_return_policy("item-b-1")
        nonexistent_policy = await repository_a.get_return_policy("item-does-not-exist")

    assert own_policy is not None
    assert own_policy.item_id == "item-a-1"
    assert cross_account_policy is None
    assert nonexistent_policy is None
    assert cross_account_policy == nonexistent_policy


@pytest.mark.integration
async def test_scoped_repository_get_return_summary_cannot_see_another_accounts_summary(
    database_engine: AsyncEngine,
) -> None:
    """``get_return_summary`` itself must refuse a foreign item's summary, in isolation.

    Same reasoning as the policy test above: item ids are globally unique, so this
    method's own account filter is the only thing standing between this call and
    another account's row - nothing downstream would ever notice if it were removed.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                _account_row("account-a"),
                _account_row("account-b"),
                _order_row("account-a", "order-a-1"),
                _order_row("account-b", "order-b-1"),
                _order_item_row("account-a", "order-a-1", "item-a-1"),
                _order_item_row("account-b", "order-b-1", "item-b-1"),
                _return_summary_row("account-a", "item-a-1"),
                _return_summary_row("account-b", "item-b-1"),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")

        own_summary = await repository_a.get_return_summary("item-a-1")
        cross_account_summary = await repository_a.get_return_summary("item-b-1")
        nonexistent_summary = await repository_a.get_return_summary("item-does-not-exist")

    assert own_summary is not None
    assert own_summary.item_id == "item-a-1"
    assert cross_account_summary is None
    assert nonexistent_summary is None
    assert cross_account_summary == nonexistent_summary


@pytest.mark.integration
async def test_replace_preference_set_never_touches_another_accounts_values(
    database_engine: AsyncEngine,
) -> None:
    """Replacing one account's preference set must leave every other account's alone."""
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add(_account_row("account-a"))
        session.add(_account_row("account-b"))
        session.add(PreferenceSetRow(account_id="account-a", updated_at=TIMESTAMP))
        session.add(
            PreferenceValueRow(account_id="account-a", value=Preference.LOWEST_COST),
        )
        session.add(PreferenceSetRow(account_id="account-b", updated_at=TIMESTAMP))
        session.add(
            PreferenceValueRow(account_id="account-b", value=Preference.NO_PRINTER),
        )
        await session.commit()

    later = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)
    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")
        result = await repository_a.replace_preference_set(
            [Preference.FASTEST_REFUND_OR_REPLACEMENT, Preference.MORE_SUSTAINABLE],
            later,
        )

    assert {value.value for value in result.values} == {
        Preference.FASTEST_REFUND_OR_REPLACEMENT,
        Preference.MORE_SUSTAINABLE,
    }

    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")
        repository_b = ScopedRepository(session, "account-b")
        a_set = await repository_a.get_preference_set()
        b_set = await repository_b.get_preference_set()

    assert a_set is not None
    assert {value.value for value in a_set.values} == {
        Preference.FASTEST_REFUND_OR_REPLACEMENT,
        Preference.MORE_SUSTAINABLE,
    }
    assert b_set is not None
    assert {value.value for value in b_set.values} == {Preference.NO_PRINTER}


@pytest.mark.integration
async def test_reset_return_summary_if_abandoned_refuses_a_row_that_has_moved_past_in_progress(
    database_engine: AsyncEngine,
) -> None:
    """A row already carrying a further-along state must not be dragged back to not_started.

    This is the precondition itself under real PostgreSQL, not just the account and
    item-id scoping every other test here proves: the stored state has to still be
    ``in_progress`` (or already ``not_started``) for the reset to apply at all.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                _account_row("account-a"),
                _order_row("account-a", "order-a-1"),
                _order_item_row("account-a", "order-a-1", "item-a-1"),
                _return_summary_row(
                    "account-a",
                    "item-a-1",
                    state=ReturnState.QR_READY,
                    observed_at=TIMESTAMP,
                ),
            ],
        )
        await session.commit()

    later = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)
    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")
        result = await repository_a.reset_return_summary_if_abandoned(
            "item-a-1",
            observed_at=later,
            updated_at=later,
        )

    assert result.outcome is ReturnSummaryCasOutcome.REFUSED
    assert result.row is not None
    assert result.row.state is ReturnState.QR_READY

    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")
        untouched = await repository_a.get_return_summary("item-a-1")

    assert untouched is not None
    assert untouched.state is ReturnState.QR_READY
    assert untouched.observed_at == TIMESTAMP


@pytest.mark.integration
async def test_reset_return_summary_if_abandoned_cannot_reach_another_accounts_item(
    database_engine: AsyncEngine,
) -> None:
    """A reset aimed at another account's item id must come back exactly like an absent one."""
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                _account_row("account-a"),
                _account_row("account-b"),
                _order_row("account-a", "order-a-1"),
                _order_row("account-b", "order-b-1"),
                _order_item_row("account-a", "order-a-1", "item-a-1"),
                _order_item_row("account-b", "order-b-1", "item-b-1"),
                _return_summary_row("account-a", "item-a-1"),
                _return_summary_row("account-b", "item-b-1"),
            ],
        )
        await session.commit()

    later = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)
    async with session_factory() as session:
        repository_a = ScopedRepository(session, "account-a")

        cross_account_result = await repository_a.reset_return_summary_if_abandoned(
            "item-b-1",
            observed_at=later,
            updated_at=later,
        )
        nonexistent_result = await repository_a.reset_return_summary_if_abandoned(
            "item-does-not-exist",
            observed_at=later,
            updated_at=later,
        )

    assert cross_account_result.outcome is ReturnSummaryCasOutcome.NOT_FOUND
    assert cross_account_result.row is None
    assert nonexistent_result.outcome is ReturnSummaryCasOutcome.NOT_FOUND
    assert nonexistent_result.row is None
    assert cross_account_result == nonexistent_result

    async with session_factory() as session:
        repository_b = ScopedRepository(session, "account-b")
        untouched = await repository_b.get_return_summary("item-b-1")

    assert untouched is not None
    assert untouched.state is ReturnState.IN_PROGRESS
    assert untouched.observed_at == TIMESTAMP


@pytest.mark.integration
async def test_reset_return_summary_if_abandoned_loses_safely_to_a_concurrent_write(
    database_engine: AsyncEngine,
) -> None:
    """A confirmed reset racing a concurrent competing write must never silently corrupt state.

    Two real connections race against the same row: one runs the reset this class
    offers, the other - standing in for a concurrent extension report of a newer,
    further-along state - runs a plain competing UPDATE with no precondition of its
    own. Whichever transaction's write actually lands first, row-level locking makes
    the second transaction's statement wait and then evaluate its own condition
    against the value the first one actually committed, never a value read before that
    commit. So the reset can only ever end up APPLIED when it is genuinely the write
    that landed while the row still satisfied its precondition - never both, and never
    a state that silently ignores the other side.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                _account_row("account-a"),
                _order_row("account-a", "order-a-1"),
                _order_item_row("account-a", "order-a-1", "item-a-1"),
                _return_summary_row(
                    "account-a",
                    "item-a-1",
                    state=ReturnState.IN_PROGRESS,
                    observed_at=TIMESTAMP,
                ),
            ],
        )
        await session.commit()

    reset_observed_at = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)
    competing_observed_at = datetime(2026, 9, 9, 8, 5, tzinfo=UTC)

    async def _run_reset() -> ReturnSummaryCasOutcome:
        async with session_factory() as session:
            repository = ScopedRepository(session, "account-a")
            result = await repository.reset_return_summary_if_abandoned(
                "item-a-1",
                observed_at=reset_observed_at,
                updated_at=reset_observed_at,
            )
            return result.outcome

    async def _run_competing_live_page_update() -> None:
        async with session_factory() as session:
            await session.execute(
                update(ReturnSummaryRow)
                .where(
                    ReturnSummaryRow.account_id == "account-a",
                    ReturnSummaryRow.item_id == "item-a-1",
                )
                .values(
                    state=ReturnState.QR_READY,
                    update_source=ReturnSummaryUpdateSource.EXTENSION_LIVE_PAGE,
                    observed_at=competing_observed_at,
                    updated_at=competing_observed_at,
                ),
            )
            await session.commit()

    reset_outcome, _ = await asyncio.gather(
        _run_reset(),
        _run_competing_live_page_update(),
    )

    async with session_factory() as session:
        repository = ScopedRepository(session, "account-a")
        final_row = await repository.get_return_summary("item-a-1")

    assert final_row is not None
    if reset_outcome is ReturnSummaryCasOutcome.APPLIED:
        # The reset's own write landed first; the competing update ran after it and
        # unconditionally overwrote it, exactly like a genuine newer live-page report
        # arriving right after a confirmed reset would.
        assert final_row.state is ReturnState.QR_READY
    else:
        # The competing write landed first, so by the time the reset's own
        # UPDATE...WHERE was evaluated the row no longer matched its precondition -
        # it lost the race and refused, leaving the competing write's state in place.
        assert reset_outcome is ReturnSummaryCasOutcome.REFUSED
        assert final_row.state is ReturnState.QR_READY
