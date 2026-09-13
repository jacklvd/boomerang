"""Account-scoped read and write access to the durable Boomerang schema.

Every ORM row that carries account data (see ``app.db.models.ORM_ROWS``) is reachable
only through :class:`ScopedRepository`, which is constructed with a single account id
and filters every query by it. Callers above ``app/db/`` cannot run an unscoped query -
``sqlalchemy.select`` and a bare ``AsyncSession`` are both banned outside this package by
the ``TID251`` ruff rule in ``pyproject.toml``.

A cross-account read is indistinguishable from a read of a row that never existed: both
return ``None`` (or an empty sequence) through the same code path. No method here raises
a distinguishable error, and no method does extra work before applying the account
filter that a genuinely-absent id would skip. The write methods preserve the same
property: a write aimed at another account's row never raises something a caller could
use to tell "refused" apart from "does not exist, or belongs to someone else" - the
result types below spell out exactly which of those a caller can distinguish and which
it cannot.

Every write method commits before returning. Nothing above this module can see the
bare session (``TID251`` again), so there is no other point in the stack where a write
made through this class could be committed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from app.db.mappers import preference_set_to_row
from app.db.models import (
    ORM_ROWS,
    UNSCOPED_ROWS,
    AccountRow,
    AuthCredentialRow,
    AuthGrantRow,
    OrderItemRow,
    OrderRow,
    PolicyRuleRow,
    PreferenceSetRow,
    PreferenceValueRow,
    ReturnPolicyRow,
    ReturnSummaryRow,
)
from app.models import PreferenceSet, ReturnState, ReturnSummaryUpdateSource

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.base import Base
    from app.models import Preference

# Every stored row that carries an account_id column, mapped to that column. A row
# declared in app.db.models.UNSCOPED_ROWS is deliberately absent here - that frozenset
# is the single source of truth for "this row carries no account scope, by design";
# this registry is checked against it below rather than re-declaring its own exceptions.
ACCOUNT_COLUMN: Final[Mapping[type[Base], InstrumentedAttribute[str]]] = {
    OrderRow: OrderRow.account_id,
    OrderItemRow: OrderItemRow.account_id,
    ReturnPolicyRow: ReturnPolicyRow.account_id,
    PolicyRuleRow: PolicyRuleRow.account_id,
    PreferenceSetRow: PreferenceSetRow.account_id,
    PreferenceValueRow: PreferenceValueRow.account_id,
    ReturnSummaryRow: ReturnSummaryRow.account_id,
    AuthGrantRow: AuthGrantRow.account_id,
    AuthCredentialRow: AuthCredentialRow.account_id,
}


def unscoped_rows(
    registry: Mapping[type[Base], InstrumentedAttribute[str]],
) -> frozenset[type[Base]]:
    """Return every row that neither ``registry`` nor ``UNSCOPED_ROWS`` accounts for.

    This is a pure function rather than a module-level assertion so it stays a coverable,
    testable check instead of an import-time side effect: a test can call it with the real
    ``ACCOUNT_COLUMN`` and assert the result is empty. ``app.db.models.UNSCOPED_ROWS`` is
    the one place a row is declared exempt from account scoping; a row missing from both
    that frozenset and this registry is a genuine gap, and shows up here rather than
    staying invisible.
    """
    return frozenset(ORM_ROWS) - frozenset(registry) - UNSCOPED_ROWS


def _is_serialization_failure(error: DBAPIError) -> bool:
    """Identify a PostgreSQL serialization failure (sqlstate ``40001``).

    Under ``REPEATABLE READ`` or ``SERIALIZABLE``, a conditional ``UPDATE`` that loses a
    race raises this instead of the plain zero-rows-affected outcome ``READ COMMITTED``
    gives the same race. Both outcomes mean the same thing - this transaction lost - so
    this is the one place that distinction gets collapsed rather than every call site
    re-deriving it.
    """
    return getattr(error.orig, "sqlstate", None) == "40001"


class ReturnSummaryCasOutcome(StrEnum):
    """What happened when a return-summary compare-and-set write was attempted."""

    APPLIED = "applied"
    """The stored row matched the precondition and now holds the new values."""

    REFUSED = "refused"
    """A row exists for this account and item, but it no longer matches the
    precondition - a later observation already moved it, or the incoming timestamp is
    stale. The caller turns this into the contract's conflict response."""

    NOT_FOUND = "not_found"
    """No row exists for this account and item. Indistinguishable from the row
    belonging to a different account - both look like this."""


@dataclass(frozen=True, slots=True)
class ReturnSummaryCasResult:
    """The outcome of one return-summary compare-and-set write, and its current row.

    ``row`` is populated for both ``APPLIED`` and ``REFUSED`` - in the first case it is
    the row after the write, in the second it is the row exactly as stored, unchanged.
    It is ``None`` only for ``NOT_FOUND``, and it never carries a hint that would let a
    caller tell a genuinely absent row apart from one that belongs to another account.
    """

    outcome: ReturnSummaryCasOutcome
    row: ReturnSummaryRow | None


class ScopedRepository:
    """Read access to one account's rows.

    Every method is filtered by the account id given at construction; there is no way
    to ask this class for a row belonging to a different account.
    """

    def __init__(self, session: AsyncSession, account_id: str) -> None:
        """Bind this repository to one account id for the lifetime of the session."""
        self._session = session
        self._account_id = account_id

    async def get_account(self) -> AccountRow | None:
        """Return this repository's own account row, or None if it does not exist."""
        return await self._session.get(AccountRow, self._account_id)

    async def get_order(self, order_id: str) -> OrderRow | None:
        """Return one order owned by this account, or None.

        orders.id is a single-column primary key (see the invariant in
        design/boomerang-account-scoping.md section 5.1), so this cannot use
        ``session.get`` with a composite identity tuple the way the composite-keyed
        child rows below do - it filters by account id explicitly instead.
        """
        result = await self._session.scalars(
            select(OrderRow).where(
                OrderRow.id == order_id,
                OrderRow.account_id == self._account_id,
            ),
        )
        return result.one_or_none()

    async def list_orders(self) -> Sequence[OrderRow]:
        """Return every order owned by this account."""
        result = await self._session.scalars(
            select(OrderRow).where(OrderRow.account_id == self._account_id),
        )
        return result.all()

    async def get_order_item(self, item_id: str) -> OrderItemRow | None:
        """Return one order item owned by this account, or None."""
        return await self._session.get(OrderItemRow, (self._account_id, item_id))

    async def get_return_policy(self, item_id: str) -> ReturnPolicyRow | None:
        """Return one item's return policy (with rules loaded) owned by this account."""
        return await self._session.get(
            ReturnPolicyRow,
            (self._account_id, item_id),
            options=[selectinload(ReturnPolicyRow.rules)],
        )

    async def get_return_summary(self, item_id: str) -> ReturnSummaryRow | None:
        """Return one item's return summary owned by this account, or None."""
        return await self._session.get(ReturnSummaryRow, (self._account_id, item_id))

    async def get_preference_set(self) -> PreferenceSetRow | None:
        """Return this account's preference set (with values loaded), or None."""
        return await self._session.get(
            PreferenceSetRow,
            self._account_id,
            options=[selectinload(PreferenceSetRow.values)],
        )

    async def list_order_items(self) -> Sequence[OrderItemRow]:
        """Return every order item this account owns, ready for a dashboard-shaped read.

        Each row comes back with its order, its return policy (and that policy's
        rules), and its return summary already loaded via ``selectinload`` - the
        account-wide, unfiltered read the dashboard's metrics need, as opposed to
        ``list_orders``, which has no path down to item level at all. ``selectinload``
        rather than a single joined statement is deliberate: items, orders, policies,
        rules and summaries is a two-level fan-out, and a join across all of it
        multiplies each item row by its rule count. Several round trips against a small
        per-account row count cost less than de-duplicating a multiplied join result,
        and it is what ``get_return_policy`` above already does for the same reason.
        """
        result = await self._session.scalars(
            select(OrderItemRow)
            .where(OrderItemRow.account_id == self._account_id)
            .options(
                selectinload(OrderItemRow.order),
                selectinload(OrderItemRow.return_policy).selectinload(ReturnPolicyRow.rules),
                selectinload(OrderItemRow.return_summary),
            ),
        )
        return result.all()

    async def replace_preference_set(
        self,
        values: Sequence[Preference],
        updated_at: datetime,
    ) -> PreferenceSetRow:
        """Replace this account's complete preference set, creating it if absent.

        This is a full replacement, never a merge: the contract's preferences write is
        a whole-set PUT with no partial-patch form, so a previously stored value absent
        from ``values`` is removed rather than left in place. The set is created on
        first write rather than requiring it to pre-exist, so an account with no stored
        preferences yet does not need a separate creation path.

        ``values`` is validated for uniqueness the same way the domain record is
        (duplicate preferences are rejected, not silently collapsed) before anything is
        written.
        """
        preferences = PreferenceSet(
            account_id=self._account_id,
            values=tuple(values),
            updated_at=updated_at,
        )

        # The parent row must exist before any child value row can be inserted - the
        # foreign key is NOT DEFERRABLE, so this order is not just tidy, it is required.
        upsert_set = pg_insert(PreferenceSetRow).values(
            account_id=self._account_id,
            updated_at=updated_at,
        )
        upsert_set = upsert_set.on_conflict_do_update(
            index_elements=["account_id"],
            set_={"updated_at": upsert_set.excluded.updated_at},
        )
        await self._session.execute(upsert_set)

        await self._session.execute(
            delete(PreferenceValueRow).where(PreferenceValueRow.account_id == self._account_id),
        )
        if preferences.values:
            await self._session.execute(
                pg_insert(PreferenceValueRow),
                [{"account_id": self._account_id, "value": value} for value in preferences.values],
            )

        await self._session.commit()
        return preference_set_to_row(preferences)

    async def reset_return_summary_if_abandoned(
        self,
        item_id: str,
        observed_at: datetime,
        updated_at: datetime,
    ) -> ReturnSummaryCasResult:
        """Apply the one supported backward transition: ``in_progress`` to ``not_started``.

        This exists for exactly one caller-confirmed transition, so update source is
        never a parameter - it is always the confirmed source, baked into the
        statement below rather than trusted from a caller. The write is a single
        conditional ``UPDATE ... WHERE ... RETURNING``: the stored state, its handoff
        evidence and its own ``observed_at`` are compared against the incoming values
        inside the same statement that performs the write, never in a prior ``SELECT``
        a later statement would have to trust. That is what lets this call race a
        live publication from another tab and still come out correct regardless of
        which one reaches the database first.

        Accepted only when, atomically: the stored state is ``in_progress`` (or already
        ``not_started`` - see below), its handoff evidence is null, and the incoming
        ``observed_at`` is at or after the row's own stored ``observed_at``.

        The idempotent repeat - a retry that finds the row already at rest in
        ``not_started`` - is folded into the same conditional statement rather than
        special-cased: a ``not_started`` row's handoff evidence is always null (the
        schema enforces this), so it only has to also satisfy the ``observed_at``
        ordering, which a same-or-later retry of the same confirmation always does.

        Returns ``NOT_FOUND`` - indistinguishable from a cross-account item - when no
        row exists for this account and item. Returns ``REFUSED`` when a row exists but
        does not currently satisfy the precondition: a later live-page observation has
        already moved it past ``in_progress``, or the incoming ``observed_at`` predates
        what is stored. A serialization failure raised under a stricter isolation level
        (PostgreSQL sqlstate ``40001``) is treated exactly like a refusal - lost the
        race - and is never retried here; blindly retrying a losing reset is exactly
        the double-application this precondition exists to prevent.
        """
        statement = (
            update(ReturnSummaryRow)
            .where(
                ReturnSummaryRow.account_id == self._account_id,
                ReturnSummaryRow.item_id == item_id,
                ReturnSummaryRow.state.in_((ReturnState.IN_PROGRESS, ReturnState.NOT_STARTED)),
                ReturnSummaryRow.handoff_evidence.is_(None),
                ReturnSummaryRow.observed_at <= observed_at,
            )
            .values(
                state=ReturnState.NOT_STARTED,
                update_source=ReturnSummaryUpdateSource.USER_CONFIRMED,
                observed_at=observed_at,
                updated_at=updated_at,
            )
            .returning(ReturnSummaryRow)
        )

        applied_row: ReturnSummaryRow | None
        try:
            result = await self._session.execute(statement)
        except DBAPIError as error:
            if not _is_serialization_failure(error):
                raise
            await self._session.rollback()
            applied_row = None
        else:
            applied_row = result.scalar_one_or_none()
            await self._session.commit()

        if applied_row is not None:
            return ReturnSummaryCasResult(ReturnSummaryCasOutcome.APPLIED, applied_row)

        existing = await self.get_return_summary(item_id)
        outcome = (
            ReturnSummaryCasOutcome.NOT_FOUND
            if existing is None
            else ReturnSummaryCasOutcome.REFUSED
        )
        return ReturnSummaryCasResult(outcome, existing)
