"""Focused PostgreSQL integration coverage for the complete ORM boundary."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import selectinload

from app.db.base import Base
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
from app.db.models import (
    AccountRow,
    AuthClientKind,
    AuthCredentialKind,
    AuthCredentialRow,
    AuthGrantRow,
    BrowserLabel,
    OrderItemRow,
    OrderRow,
    PreferenceSetRow,
    ReturnPolicyRow,
)
from app.db.session import build_session_factory
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

EXPECTED_TABLES = {
    "accounts",
    "orders",
    "order_items",
    "return_policies",
    "policy_rules",
    "preference_sets",
    "preference_values",
    "return_summaries",
    "pairing_requests",
    "auth_grants",
    "auth_credentials",
}
EXPECTED_ENUM_TYPES = {
    "fact_origin",
    "handoff_evidence",
    "policy_eligibility",
    "preference",
    "return_state",
    "return_summary_update_source",
    "pairing_status",
    "browser_label",
    "auth_client_kind",
    "auth_credential_kind",
    "grant_revocation_reason",
}
ENUM_TYPES_QUERY = text(
    """
    SELECT enum_type.typname
    FROM pg_type AS enum_type
    JOIN pg_namespace AS namespace ON namespace.oid = enum_type.typnamespace
    WHERE enum_type.typtype = 'e'
      AND namespace.nspname = current_schema()
    """,
)


@dataclass(frozen=True)
class _ExpectedGraph:
    account: Account
    order: Order
    item: OrderItem
    policy: ReturnPolicy
    preferences: PreferenceSet
    summary: ReturnSummary


async def _schema_objects(engine: AsyncEngine) -> tuple[set[str], set[str]]:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names()),
        )
        enum_names = set((await connection.execute(ENUM_TYPES_QUERY)).scalars())
    return table_names, enum_names


def _expected_graph() -> _ExpectedGraph:
    timestamp = datetime(2026, 9, 8, 16, 30, tzinfo=UTC)
    return _ExpectedGraph(
        account=Account(
            id="account-1",
            google_subject="google-subject-1",
            email="returner@example.com",
            display_name="Returner",
            avatar_url="https://example.com/avatar.png",
            created_at=timestamp,
            updated_at=timestamp,
        ),
        order=Order(
            id="order-1",
            account_id="account-1",
            retailer_key="example-retailer",
            retailer_name="Example Retailer",
            retailer_order_reference="ORDER-1001",
            ordered_on=date(2026, 8, 28),
            created_at=timestamp,
            updated_at=timestamp,
        ),
        item=OrderItem(
            id="item-1",
            order_id="order-1",
            description="Running shoes",
            variant="Blue / 9",
            quantity=1,
            price=Money(amount_minor=12_500, currency="USD"),
            delivered_on=date(2026, 9, 2),
            created_at=timestamp,
            updated_at=timestamp,
        ),
        policy=ReturnPolicy(
            item_id="item-1",
            eligibility=PolicyEligibility.ELIGIBLE,
            return_by=SourcedDate(
                value=date(2026, 9, 30),
                origin=FactOrigin.RETAILER_STATED,
                confidence=0.99,
            ),
            fee=SourcedMoney(
                value=Money(amount_minor=0, currency="USD"),
                origin=FactOrigin.RETAILER_STATED,
                confidence=1.0,
            ),
            rules=(
                PolicyRule(
                    id="original-condition",
                    text="Item must be in original condition.",
                    origin=FactOrigin.RETAILER_STATED,
                    confidence=0.97,
                ),
            ),
            version=1,
            updated_at=timestamp,
        ),
        preferences=PreferenceSet(
            account_id="account-1",
            values=(Preference.NO_PRINTER,),
            updated_at=timestamp,
        ),
        summary=ReturnSummary(
            item_id="item-1",
            state=ReturnState.HANDED_TO_CARRIER,
            update_source=ReturnSummaryUpdateSource.USER_CONFIRMED,
            handoff_evidence=HandoffEvidence.USER_CONFIRMED,
            observed_at=timestamp,
            updated_at=timestamp,
        ),
    )


def _account_graph_to_row(expected: _ExpectedGraph) -> AccountRow:
    account_id = expected.account.id
    account_row = account_to_row(expected.account)
    order_row = order_to_row(expected.order)
    item_row = order_item_to_row(account_id, expected.item)

    item_row.return_policy = return_policy_to_row(account_id, expected.policy)
    item_row.return_summary = return_summary_to_row(account_id, expected.summary)
    order_row.items = [item_row]
    account_row.orders = [order_row]
    account_row.preference_set = preference_set_to_row(expected.preferences)
    return account_row


def _assert_domain_graph(row: AccountRow, expected: _ExpectedGraph) -> None:
    assert account_from_row(row) == expected.account
    assert len(row.orders) == 1
    order_row = row.orders[0]
    assert order_from_row(order_row) == expected.order

    assert len(order_row.items) == 1
    item_row = order_row.items[0]
    assert order_item_from_row(item_row) == expected.item

    assert item_row.return_policy is not None
    assert return_policy_from_row(item_row.return_policy) == expected.policy
    assert item_row.return_summary is not None
    assert return_summary_from_row(item_row.return_summary) == expected.summary

    assert row.preference_set is not None
    assert preference_set_from_row(row.preference_set) == expected.preferences


@pytest.mark.integration
async def test_schema_lifecycle(database_engine: AsyncEngine) -> None:
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    assert await _schema_objects(database_engine) == (EXPECTED_TABLES, EXPECTED_ENUM_TYPES)

    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

    assert await _schema_objects(database_engine) == (set(), set())


@pytest.mark.integration
async def test_complete_persistence_round_trip(database_engine: AsyncEngine) -> None:
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    expected = _expected_graph()
    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add(_account_graph_to_row(expected))
        await session.commit()

    statement = select(AccountRow).options(
        selectinload(AccountRow.orders)
        .selectinload(OrderRow.items)
        .selectinload(OrderItemRow.return_policy)
        .selectinload(ReturnPolicyRow.rules),
        selectinload(AccountRow.orders)
        .selectinload(OrderRow.items)
        .selectinload(OrderItemRow.return_summary),
        selectinload(AccountRow.preference_set).selectinload(PreferenceSetRow.values),
    )
    async with session_factory() as session:
        loaded_account = (await session.scalars(statement)).one()
        _assert_domain_graph(loaded_account, expected)


@pytest.mark.integration
async def test_composite_foreign_key_rejects_cross_account_order_item(
    database_engine: AsyncEngine,
) -> None:
    """A child row cannot be inserted against a parent that belongs to another account.

    This is the account-hop the composite foreign keys exist to close off: see
    design/boomerang-account-scoping.md sections 5 and 5.1.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    timestamp = datetime(2026, 9, 8, 16, 30, tzinfo=UTC)
    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                AccountRow(
                    id="account-a",
                    google_subject="google-subject-a",
                    email=None,
                    display_name=None,
                    avatar_url=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
                AccountRow(
                    id="account-b",
                    google_subject="google-subject-b",
                    email=None,
                    display_name=None,
                    avatar_url=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
            ],
        )
        session.add(
            OrderRow(
                id="order-owned-by-a",
                account_id="account-a",
                retailer_key="example-retailer",
                retailer_name="Example Retailer",
                retailer_order_reference=None,
                ordered_on=None,
                created_at=timestamp,
                updated_at=timestamp,
            ),
        )
        await session.commit()

    async with session_factory() as session:
        # account-b claiming an item against account-a's order: the FK target
        # (account_id, order_id) = ("account-b", "order-owned-by-a") does not exist.
        session.add(
            OrderItemRow(
                account_id="account-b",
                id="item-hopped",
                order_id="order-owned-by-a",
                description="Hopped item",
                variant=None,
                quantity=1,
                price_amount_minor=None,
                price_currency=None,
                delivered_on=None,
                created_at=timestamp,
                updated_at=timestamp,
            ),
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
async def test_second_order_with_unreadable_reference_is_rejected_not_duplicated(
    database_engine: AsyncEngine,
) -> None:
    """A rescan that cannot read the retailer's order reference must fail loudly.

    Without NULLS NOT DISTINCT on uq_orders_retailer_reference, PostgreSQL treats two NULL
    references for the same (account_id, retailer_key) as distinct, so this insert would
    silently succeed and duplicate the order - see DAL-3 in the low-level design review.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    timestamp = datetime(2026, 9, 8, 16, 30, tzinfo=UTC)
    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add(
            AccountRow(
                id="account-a",
                google_subject="google-subject-a",
                email=None,
                display_name=None,
                avatar_url=None,
                created_at=timestamp,
                updated_at=timestamp,
            ),
        )
        session.add(
            OrderRow(
                id="order-first-scan",
                account_id="account-a",
                retailer_key="example-retailer",
                retailer_name="Example Retailer",
                retailer_order_reference=None,
                ordered_on=None,
                created_at=timestamp,
                updated_at=timestamp,
            ),
        )
        await session.commit()

    async with session_factory() as session:
        session.add(
            OrderRow(
                id="order-rescan",
                account_id="account-a",
                retailer_key="example-retailer",
                retailer_name="Example Retailer",
                retailer_order_reference=None,
                ordered_on=None,
                created_at=timestamp,
                updated_at=timestamp,
            ),
        )
        with pytest.raises(IntegrityError):
            await session.commit()


RECONCILIATION_QUERY = text(
    """
    SELECT i.id
    FROM order_items i
    JOIN orders o ON i.order_id = o.id
    WHERE i.account_id <> o.account_id
    """,
)


@pytest.mark.integration
async def test_auth_grant_id_uniqueness_is_enforced_across_accounts(
    database_engine: AsyncEngine,
) -> None:
    """A second account cannot mint a grant reusing another account's grant id.

    auth_grants has a composite primary key (account_id, id), so nothing about the
    primary key itself stops two different accounts from each having a row with the
    same id - only the separate uq_auth_grants_id constraint does. Without it, a
    credential row's composite foreign key to (account_id, grant_id) could be satisfied
    by hopping a credential onto a same-id grant under a different account.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    timestamp = datetime(2026, 9, 8, 16, 30, tzinfo=UTC)
    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                AccountRow(
                    id="account-a",
                    google_subject="google-subject-a",
                    email=None,
                    display_name=None,
                    avatar_url=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
                AccountRow(
                    id="account-b",
                    google_subject="google-subject-b",
                    email=None,
                    display_name=None,
                    avatar_url=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
            ],
        )
        session.add(
            AuthGrantRow(
                account_id="account-a",
                id="grant-shared-id",
                client_kind=AuthClientKind.EXTENSION,
                browser_label=BrowserLabel.CHROME,
                created_at=timestamp,
                last_used_at=timestamp,
                idle_expires_at=timestamp,
                absolute_expires_at=timestamp,
                revoked_at=None,
                revoked_reason=None,
            ),
        )
        await session.commit()

    async with session_factory() as session:
        session.add(
            AuthGrantRow(
                account_id="account-b",
                id="grant-shared-id",
                client_kind=AuthClientKind.EXTENSION,
                browser_label=BrowserLabel.CHROME,
                created_at=timestamp,
                last_used_at=timestamp,
                idle_expires_at=timestamp,
                absolute_expires_at=timestamp,
                revoked_at=None,
                revoked_reason=None,
            ),
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
async def test_composite_foreign_key_rejects_cross_account_auth_credential(
    database_engine: AsyncEngine,
) -> None:
    """A credential cannot be inserted against a grant that belongs to another account.

    The MATCH FULL composite foreign key on auth_credentials(account_id, grant_id) is
    what stops a credential row from being hopped onto a same-id grant under a
    different account, once uq_auth_grants_id has made that id globally unique.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    timestamp = datetime(2026, 9, 8, 16, 30, tzinfo=UTC)
    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add_all(
            [
                AccountRow(
                    id="account-a",
                    google_subject="google-subject-a",
                    email=None,
                    display_name=None,
                    avatar_url=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
                AccountRow(
                    id="account-b",
                    google_subject="google-subject-b",
                    email=None,
                    display_name=None,
                    avatar_url=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
            ],
        )
        session.add(
            AuthGrantRow(
                account_id="account-a",
                id="grant-owned-by-a",
                client_kind=AuthClientKind.EXTENSION,
                browser_label=BrowserLabel.CHROME,
                created_at=timestamp,
                last_used_at=timestamp,
                idle_expires_at=timestamp,
                absolute_expires_at=timestamp,
                revoked_at=None,
                revoked_reason=None,
            ),
        )
        await session.commit()

    async with session_factory() as session:
        # account-b claiming a credential against account-a's grant: the FK target
        # (account_id, grant_id) = ("account-b", "grant-owned-by-a") does not exist.
        session.add(
            AuthCredentialRow(
                account_id="account-b",
                id="credential-hopped",
                grant_id="grant-owned-by-a",
                kind=AuthCredentialKind.ACCESS,
                credential_hash="hopped-credential-hash",
                generation=None,
                issued_at=timestamp,
                expires_at=timestamp,
                rotated_at=None,
                revoked_at=None,
            ),
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
async def test_order_item_account_id_never_diverges_from_its_order(
    database_engine: AsyncEngine,
) -> None:
    """Standing reconciliation assertion: see design/boomerang-account-scoping.md section 5.

    This must always find zero rows. It documents the invariant the composite foreign keys
    already enforce, in executable form, so a future migration that drops or weakens one of
    those constraints fails this test even before it produces a real divergent row.
    """
    async with database_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    expected = _expected_graph()
    session_factory = build_session_factory(database_engine)
    async with session_factory() as session:
        session.add(_account_graph_to_row(expected))
        await session.commit()

    async with database_engine.connect() as connection:
        divergent_items = (await connection.execute(RECONCILIATION_QUERY)).scalars().all()
    assert divergent_items == []
