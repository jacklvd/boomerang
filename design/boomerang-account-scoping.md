> **STATUS: ACCEPTED — 2026-09-13.**
>
> The user accepted the recommendation in section 9 on 2026-09-13: **Option A and Option B together,
> as one change** — `account_id` threaded through the schema as the leading primary-key column with
> composite foreign keys, plus an account-scoped repository boundary the unscoped session cannot
> escape. Option C remains the named follow-on; Option D stays rejected. The decision was taken
> under deadline, deliberately choosing to proceed with the design as it stands rather than revise
> it further. This document is therefore **normative** for account-scoping enforcement, and it is
> the answer to the low-level design review's `DAL-2`.
>
> The decision is registered in [`../plan/boomerang-decisions.md`](../plan/boomerang-decisions.md)
> as `MIG-16`. Section 10 lists the server, test and design-document changes acceptance requires;
> those are outstanding work, not changes this document has made. Section 12's conflicts stand as
> recorded — in particular, accepting this means accepting that the low-level design's deferral of
> physical schema, index and constraint decisions has already lapsed in practice.
>
> Written 2026-09-13, in response to the low-level design review of the same date, whose finding
> `DAL-2` is the single blocking data-access-layer problem. Accepted the same day.

---

# Boomerang — Account Scoping Enforcement Proposal

> **Verification update, 2026-09-13.** Two spikes referenced below as unexecuted have since run. Spike 1
> (SQLAlchemy 2.0.52 — the version pinned in `server/uv.lock` — sync and async, SQLite) settles the
> `session.get` question in section 3, Option A, and the mypy question in section 4. Spike 2
> (PostgreSQL 17.11, image `postgres:17.11-alpine3.24` — the tag `server/compose.integration.yml`
> pins — SQLAlchemy 2.0.52, psycopg 3.3.5) settles the composite-foreign-key questions in section 5.
> Both ran against throwaway schemas outside this repository; nothing under `server/` was modified, no
> dependency was added to `server/uv.lock`, and no container from this repository's compose files was
> started. Findings are folded into sections 3, 4 and 5 below, each marked **Verified** where it
> applies. Two findings sharpen rather than merely confirm the original text and are marked
> accordingly: the `orders.id` invariant in section 5, and the `MATCH SIMPLE` / `NOT NULL` requirement,
> also in section 5.

---

## 1. What was verified, and two premises that the repository contradicts

Every claim below was checked against the working tree today. Where I could not execute something,
I say so rather than asserting it.

### 1.1 Verified in the schema

| Fact | Evidence |
|---|---|
| `accounts.id` is the account key | `server/app/db/models.py:79` |
| `orders.account_id` is the only account column outside the preference tables | `server/app/db/models.py:115` |
| `order_items` carries `order_id` and no account column | `server/app/db/models.py:153-154` |
| `return_policies` is keyed by `item_id` alone | `server/app/db/models.py:217` |
| `policy_rules` is keyed by `(item_id, id)` and hangs off `return_policies.item_id` | `server/app/db/models.py:248-252` |
| `return_summaries` is keyed by `item_id` alone | `server/app/db/models.py:309` |
| `preference_sets` and `preference_values` are account-keyed | `server/app/db/models.py:265`, `server/app/db/models.py:281` |
| Every relationship declares `lazy="raise"` | `server/app/db/models.py`, all eight rows |
| The account predicate has no index beyond `ix_orders_account_id` | `server/app/db/models.py:111` |

The order-graph reach from a summary is therefore
`return_summaries.item_id` → `order_items.id` → `order_items.order_id` → `orders.id` →
`orders.account_id`: two joins, required by nothing.

### 1.2 Verified in the application

There is no data-access layer at all yet. `server/app/db/session.py` contains two free functions,
`build_async_engine` and `build_session_factory`, and neither has a caller anywhere in `app/`.
`server/app/api/__init__.py` and `server/app/routes/__init__.py` are one line each. `server/app/main.py`
registers `/health` and nothing else. `server/app/db/mappers.py` converts between domain records and
ORM rows and is pure.

This matters more than it might look: **the enforcement device is being chosen before the code it
would constrain exists.** Nothing has to be unwound. That is the cheapest this decision will ever be.

### 1.3 Premise in the brief that the repository contradicts: migration tooling

The brief states there is "Alembic-style migration tooling in the server." **There is not.** I looked
for it four ways:

- `server/pyproject.toml` dependencies are `anthropic[bedrock]`, `fastapi[standard]`, `mangum`,
  `psycopg[binary]`, `sqlalchemy[asyncio]`; the dev group is `mypy`, `pip-audit`, `pytest`,
  `pytest-asyncio`, `pytest-cov`, `ruff`. No migration library in either.
- `server/uv.lock` contains no `alembic` package entry.
- There is no `alembic.ini`, no `migrations/`, no `versions/` directory anywhere outside `.venv/`.
- `server/Makefile` has no migration target.

The review says the same thing independently in its `DAL-5` finding. The schema is currently created
only by `Base.metadata.create_all()` inside the integration tests, which `server/AGENTS.md` correctly
labels test infrastructure and not production database setup.

### 1.4 Premise in the brief that the repository contradicts: data-bearing tables

The brief states the schema "already exists with data-bearing tables." In the sense of tables that
are declared, yes. In the sense of tables holding data anyone would lose, no:

- `infra/main.tf` declares a VPC, subnets, route tables, a security group, an IAM role and policies,
  an instance profile and one EC2 instance. There is no `aws_db_instance` and no `aws_rds_cluster`.
  `infra/AGENTS.md` and the decision record both describe `infra/` as an earlier scaffold that is not
  the settled topology.
- `server/.env.example` offers exactly one database variable, `TEST_DATABASE_URL`, and describes it
  as the disposable local PostgreSQL used only by integration tests.
- `server/compose.integration.yml` mounts the PostgreSQL data directory on `tmpfs`, so the data is
  destroyed with the container.
- `server/AGENTS.md` states that local PostgreSQL exists only as a disposable test harness.

**There is no deployed database and no persisted row.** Section 8 is written accordingly: the
migration question here is a code-change question, not a downtime question.

---

## 2. The threat model, precisely

### 2.1 The shape of the defect

Three of the eight tables are addressed by a key the caller supplies and carry no column that ties
that key to an account. The wire contract exposes exactly one such key: `item_id`. Two routes take it
in the path.

The consequence is not that a correct query is hard to write. It is that the **incorrect query is
shorter, obvious, type-correct, and indistinguishable from the correct one by reading it.**

```python
# What a contributor writes. It compiles, mypy --strict accepts it, and it returns
# whichever account happens to own that item.
summary = await session.get(ReturnSummaryRow, item_id)
```

```python
# What is actually required, today, on every item-addressed read.
summary = (
    await session.scalars(
        select(ReturnSummaryRow)
        .join(OrderItemRow, ReturnSummaryRow.item_id == OrderItemRow.id)
        .join(OrderRow, OrderItemRow.order_id == OrderRow.id)
        .where(
            ReturnSummaryRow.item_id == item_id,
            OrderRow.account_id == account_id,
        )
    )
).one_or_none()
```

Nothing in the schema, the type system, the linter or the test suite prefers the second. The only
thing that produces it is a contributor who happens to remember.

### 2.2 What `lazy="raise"` does and does not do

`lazy="raise"` is on every relationship in `server/app/db/models.py`, and it is a good control — for
a different failure. It fires when code traverses an unloaded relationship, which catches accidental
N+1 loads and accidental lazy fan-out from a detached row. It cannot fire on
`session.get(ReturnSummaryRow, item_id)`, because that statement never touches a relationship. The
strongest control currently in the persistence layer is orthogonal to the strongest hole in it.

There is a second-order effect worth naming: because `lazy="raise"` forces every read to be written
as an explicit query with explicit loading, contributors will be writing `select(...)` statements by
hand constantly. The volume of hand-written queries in this codebase will be high. A control that
depends on each of those being written correctly is a control with a high exposure count.

### 2.3 Exposure by table

Distance is the number of joins required to reach `orders.account_id`.

| Table | Account column | Distance | Reachable by caller-supplied key | Consequence of the naive query |
|---|---|---|---|---|
| `accounts` | is the account | — | No | None. The only key is the principal's own. |
| `orders` | `account_id` | 0 | No (no route takes an `order_id`) | A missing predicate returns every account's orders, but the fix is a column that already exists. |
| `order_items` | none | 1 | **Yes** (`item_id`) | Returns another account's item description, variant, quantity, price and delivery date. |
| `return_policies` | none | 2 | **Yes** (same `item_id`) | Returns another account's eligibility, deadline, fee and provenance. |
| `policy_rules` | none | 2 via `order_items`, 3 via `return_policies` | **Yes** (same `item_id`) | Returns another account's normalized policy rule text. |
| `return_summaries` | none | 2 | **Yes** (same `item_id`) | Returns **and overwrites** another account's return state. |
| `preference_sets` | `account_id` (primary key) | 0 | No | None. A primary-key lookup is already scoped. |
| `preference_values` | `account_id` (primary key) | 0 | No | None. Same. |

The table is its own argument. **The three tables with an account column have no finding against
them, and the four without one are the entire finding.** The schema already demonstrates the fix on
the half of itself that is not broken.

### 2.4 Exposure by route

The contract freezes seven v1 routes. Each is classified by *how* it is exposed, because the three
kinds need different answers.

| # | Route | Addressed by | Tables touched | Exposed | How |
|---|---|---|---|---|---|
| 1 | `GET /v1/me` | principal | `accounts` | **No** | The only key is the account the authentication boundary resolved. There is no caller-supplied identifier to substitute. |
| 2 | `GET /v1/dashboard` | principal | `orders`, `order_items`, `return_policies`, `policy_rules`, `return_summaries` | **Yes — by omission** | See below. |
| 3 | `GET /v1/items/{item_id}` | **caller-supplied `item_id`** | `order_items`, `orders`, `return_policies`, `policy_rules`, `return_summaries` | **Yes — directly, on five tables at once** | See below. |
| 4 | `GET /v1/preferences` | principal | `preference_sets`, `preference_values` | **No** | Both tables are keyed by `account_id`; the scoped query is the primary-key query. |
| 5 | `PUT /v1/preferences` | principal | `preference_sets`, `preference_values` | **No** | Same. A replace-the-set write addressed by `account_id` cannot reach another account. |
| 6 | `PUT /v1/items/{item_id}/return-summary` | **caller-supplied `item_id`** | `return_summaries` (read **and write**), `order_items` | **Yes — directly, and it is the only write** | See below. |
| 7 | `DELETE /v1/account` | principal | all eight | **Yes — by cascade correctness, not by addressing** | See below. |

**Route 3, `GET /v1/items/{item_id}`.** The detail response embeds the item, its order's retailer and
reference, its policy, its policy rules and its return summary. A handler that resolves the item by
bare primary key and then walks outward returns another account's complete return candidate with a
`200`. Five tables are disclosed by one forgotten join, and four of the five have no column that
would have made the omission visible in review.

**Route 6, `PUT /v1/items/{item_id}/return-summary`.** The worst of the seven, because it is a write.
The handler must read the current summary to validate the transition, then write the new state. Both
halves are addressed by `item_id`. An unscoped implementation lets any authenticated caller drive
another account's item from `not_started` to `label_ready` — silently corrupting that account's
dashboard, its closing-soon count, and its next-action derivation. It is also the route with the most
tempting shortcut, since `session.get(ReturnSummaryRow, item_id)` reads as the natural way to fetch
the row you are about to replace.

There is a second, subtler defect on this route even if scoping is present but ordered wrongly. The
contract defines `409 state_transition_not_allowed` and `409 state_blocked`. If the transition
validator runs before the ownership predicate, a cross-account item returns `409` instead of `404` —
which confirms the item exists *and* leaks its current state, since only certain current states
produce that `409`. Ordering is part of the contract requirement, not an implementation detail.

**Route 2, `GET /v1/dashboard`.** Not addressed by a caller key, so there is nothing to substitute —
but the contract requires metrics computed over the account-wide unfiltered population while the
candidate list is filtered and paginated. That means at least two queries, one of which is an
aggregate. An aggregate over `order_items` or `return_summaries` written without the two-level join
returns a figure computed across every account in the database. The failure is quiet: the dashboard
still renders, the number is merely wrong and derived from other people's data. The review's `DAL-6`
finding notes separately that this is the heaviest read in v1 and is unspecified.

**Route 7, `DELETE /v1/account`.** The principal names the account, so there is no cross-account
*read*. The exposure is the inverse: the review's `DAL-4` finding establishes that no relationship
declares `delete` or `delete-orphan` and no foreign key declares `ondelete`, so the cascade must be
hand-written across a five-level chain in reverse dependency order. A hand-written cascade that
reaches `return_summaries` by a collected list of item identifiers has no account predicate on its
final statement. Under-deletion leaves a deleted account's rows behind; a mis-derived identifier set
deletes someone else's. Deletion is the one place where the absence of an account column turns a read
bug into a data-loss bug.

### 2.5 Who reaches it

Two populations, and they need to be separated because they justify different strengths of control.

**The honest bug — the realistic case, and the one the mechanism must stop.** No attacker is required.
It needs only a contributor who writes route 3 or route 6 the short way. `mypy --strict` passes.
`ruff` with `select = ["ALL"]` passes. The unit suite passes, because a unit test with one account's
fixtures cannot tell a scoped query from an unscoped one — *every* query returns the right answer
when only one account exists. This is the crux of the testability problem in section 7: the default
test fixture actively conceals the defect.

**The deliberate attacker.** Requires an authenticated account plus another account's `item_id`. The
contract's examples are ULID-shaped (`item_01K4A58C80H75R0N9FK6E4K2AQ`), and a ULID's 80 random bits
are not guessable. So the direct-guessing path is weak. But unguessability is not a control, and
three paths do not require guessing:

1. **Identifier minting is unresolved and may be caller-influenced.** The review's `DAL-3` finding
   observes that order and item identifiers are caller-supplied opaque text primary keys and that
   nothing states who mints them. I confirmed there is no minting code: `server/app/db/mappers.py`
   passes `id` straight through from the domain record, and `server/app/models/domain.py` declares
   `id` as an opaque identifier with no server-side generator. **I could not verify that any
   server-side minting path exists, because none does yet.** If ingestion ever accepts an identifier
   that a retailer page or a normalization output influenced, guessing becomes *choosing*, and the
   two-level join is the only thing between a chosen identifier and another account's row.
2. **Identifiers are not secrets and are not treated as such.** `item_id` appears in the wire
   contract, in dashboard responses, in item-detail responses, in extension storage, and in every
   URL path for routes 3 and 6. Any control whose strength rests on the identifier staying private
   is one screenshot, one support ticket, or one shared browser profile from failing.
3. **A stale client is a cross-account request with no attacker at all.** A dashboard or extension
   that caches an `item_id` across an account switch issues route 3 against the wrong principal by
   accident. The server cannot tell that request apart from an attack, and must not need to.

The conclusion is not "the risk is low because ULIDs are long." It is that **the mechanism must hold
for an arbitrary caller-supplied identifier, because the system's own identity story does not yet
guarantee anything about where identifiers come from.**

---

## 3. Options

Four mechanisms, scored honestly, plus two set aside. The scoring axis that matters most is stated
first, because it separates the options more than cost does: **does the naive query fail to compile,
fail to run, or fail to return rows — or does it work?**

### Option A — Thread `account_id` through the schema with composite keys and composite foreign keys

Add `account_id` to `order_items`, `return_policies`, `policy_rules` and `return_summaries`; make it
the **leading column of each primary key**; and make every foreign key composite so the column is
tied to its parent by referential integrity rather than by discipline.

```python
class OrderRow(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "retailer_key", "retailer_order_reference",
            name="uq_orders_retailer_reference",
        ),
        # The target a composite child foreign key points at. Not a new uniqueness
        # claim - id is already unique - it exists so children can carry the account.
        UniqueConstraint("account_id", "id", name="uq_orders_account_id_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))


class OrderItemRow(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        # id stays globally unique so the wire identifier still names at most one item.
        UniqueConstraint("id", name="uq_order_items_id"),
        ForeignKeyConstraint(
            ["account_id", "order_id"],
            ["orders.account_id", "orders.id"],
            name="fk_order_items_account_id_orders",
        ),
        Index("ix_order_items_account_id_order_id", "account_id", "order_id"),
        # existing check constraints unchanged
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    order_id: Mapped[str] = mapped_column(Text)


class ReturnSummaryRow(Base):
    __tablename__ = "return_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "item_id"],
            ["order_items.account_id", "order_items.id"],
            name="fk_return_summaries_account_id_order_items",
        ),
        # existing check constraints unchanged
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
```

`return_policies` takes the same treatment as `return_summaries`. `policy_rules` becomes
`(account_id, item_id, id)` with a composite foreign key onto `return_policies (account_id, item_id)`.

**Why the primary key and not just a column.** `id` on `order_items` is already unique, so the
composite primary key adds no uniqueness. Its purpose is **addressing**: a composite primary key makes
every by-key lookup and every referencing foreign key carry the account, whether the author was
thinking about isolation or not. It is an ergonomic control expressed in DDL. `UNIQUE (id)` is kept
alongside it so the wire contract's assumption that an `item_id` names at most one item survives.

**What it catches.** Every by-key access form. `session.get(ReturnSummaryRow, item_id)` no longer has
a valid identity: SQLAlchemy's documented behaviour for a scalar identity against a two-column primary
key is to raise `InvalidRequestError` rather than guess. It raises on *every* call, in the first
manual test, not only under a cross-account fixture — a deterministic failure, not a data-dependent
one. It also makes `ACCOUNT_COLUMN[entity] == account_id` a legal predicate for all seven non-account
tables, which is what makes Options B, C and D cheap and reviewable instead of bespoke per table.

> **Verified — spike executed 2026-09-13.** SQLAlchemy 2.0.52 (the version pinned in
> `server/uv.lock`), sync and async, against SQLite. `session.get(ReturnSummaryRow, "item-1")` against
> the two-column primary key raises, unconditionally, on every run:
>
> ```
> sqlalchemy.exc.InvalidRequestError: Incorrect number of values in identifier to formulate primary
> key for session.get(); primary key columns are 'return_summaries.account_id','return_summaries.item_id'
> ```
>
> `get_one()` behaves identically, and so does the legacy `session.query(ReturnSummaryRow).get("item-1")`
> — it raises the **same** `InvalidRequestError`, after a `LegacyAPIWarning`; the legacy API is not a
> bypass. The correct call, `session.get(ReturnSummaryRow, (account_id, item_id))`, works. The
> **reversed** tuple, `(item_id, account_id)`, does not raise — it silently returns `None`, because
> identity-key order follows mapping declaration order, not argument order, and is a second failure
> mode worth naming alongside the raise. The dict form, `{"account_id": ..., "item_id": ...}`, works
> and is order-insensitive, which is the safer spelling for exactly that reason.
>
> The raise happens inside the ORM's Python-side identity-key construction, before any SQL is built or
> a connection is used. It is therefore dialect-independent by construction — the SQLite result
> transfers to PostgreSQL without needing to be separately re-run there. This closes the question this
> callout previously left open: it was "SQLAlchemy's documented behaviour, not something I observed";
> it is now observed.
>
> **mypy does not see this, and the root cause is worth recording.** I also ran `mypy --strict` over
> the same call site: `Success: no issues found`. The cause is in `sqlalchemy/orm/session.py`, which
> types `session.get`'s identifier parameter as `_PKIdentityArgument = Union[Any, Tuple[Any, ...]]` — a
> `Union` containing `Any` collapses to `Any`, so `ident` is statically unconstrained no matter what is
> passed. The failure this section describes is real, but it is **runtime-only**; nothing in this
> proposal claims or relies on static detection of it, and section 4's mypy claim is confirmed on the
> same grounds.

**What it FAILS to catch.** The other access form, unchanged:

```python
# Option A does nothing about this. It still compiles, still runs, still returns
# another account's row.
summary = (
    await session.scalars(
        select(ReturnSummaryRow).where(ReturnSummaryRow.item_id == item_id)
    )
).one_or_none()
```

> **Measured — spike executed 2026-09-13.** The same spike ran exactly this statement —
> `select(ReturnSummaryRow).where(ReturnSummaryRow.item_id == "item-1")`, no account predicate — against
> a database seeded with two accounts each owning an `item-1`. It returned **both** rows: `acct-A/item-1`
> and `acct-B/item-1`. The composite primary key changes nothing about this query's result; it is
> exactly as exposed as it was before Option A. This is why B, C or D still has to exist.

A schema cannot stop a hand-written predicate from being incomplete. Option A converts "you must
remember a two-level join" into "you must remember one column equality" and kills the shortest unsafe
form outright — a large reduction in both the probability and the reviewability of the mistake, and
**not** a guarantee. Scored alone, Option A is a strong *enabler* and a partial control.

**Cost.** Four column additions, four primary-key changes, four composite foreign keys, two new unique
constraints, two index changes, mapper signature changes, test updates. All of it in one file plus its
tests, in a codebase with no deployed data (section 1.4). Also: `Index("ix_orders_account_id", ...)`
at `server/app/db/models.py:111` becomes redundant once `uq_orders_account_id_id` exists, since the
unique index leads with the same column. And composite constraints must be **named explicitly**,
because the naming convention in `server/app/db/base.py` interpolates `column_0_name` and therefore
only ever sees the first column.

**What it breaks.** `server/app/db/mappers.py` builds rows from domain records that carry no account:
`OrderItem` has `order_id` and no `account_id` (`server/app/models/domain.py:160-164`), and the same
is true of `ReturnPolicy` and `ReturnSummary`. Two ways out, and they are not equivalent — see
section 10.

---

### Option B — An account-scoped repository boundary the unscoped session cannot escape

A `ScopedRepository` whose only constructor takes the principal, holding the session privately. Above
`app/db/`, `AsyncSession` and `select` are not importable at all.

```python
# app/db/scope.py

@dataclass(frozen=True, slots=True)
class AccountScope:
    """The only value that authorizes a read.

    Produced by the authentication boundary. Never parsed from a request body,
    path segment or query parameter.
    """

    account_id: str


ACCOUNT_COLUMN: Final[Mapping[type[Base], InstrumentedAttribute[str]]] = {
    OrderRow: OrderRow.account_id,
    OrderItemRow: OrderItemRow.account_id,
    ReturnPolicyRow: ReturnPolicyRow.account_id,
    PolicyRuleRow: PolicyRuleRow.account_id,
    PreferenceSetRow: PreferenceSetRow.account_id,
    PreferenceValueRow: PreferenceValueRow.account_id,
    ReturnSummaryRow: ReturnSummaryRow.account_id,
}


def unscoped_rows(
    registry: Mapping[type[Base], InstrumentedAttribute[str]],
) -> frozenset[type[Base]]:
    """Return every stored row that declares no account column."""
    return frozenset(ORM_ROWS) - frozenset(registry) - {AccountRow}


class ScopedRepository:
    """Every query this object produces already carries the account predicate."""

    def __init__(self, session: AsyncSession, scope: AccountScope) -> None:
        self._session = session
        self._scope = scope

    def _select(self, entity: type[RowT]) -> Select[tuple[RowT]]:
        return select(entity).where(ACCOUNT_COLUMN[entity] == self._scope.account_id)

    async def get(self, entity: type[RowT], key: str) -> RowT | None:
        """Fetch one row by its account-scoped identity, or None."""
        return await self._session.get(entity, (self._scope.account_id, key))
```

Two properties carry the weight, and they are worth separating because only one of them is common
practice:

1. **There is no method that returns an unscoped query.** `_select` is the only statement factory and
   it is private; `self._session` is private. A caller holding a `ScopedRepository` has no expressible
   way to get an unfiltered statement.
2. **`unscoped_rows` is an exhaustiveness check over the row registry.** `ORM_ROWS` already exists at
   `server/app/db/models.py:321-330` and lists every mapped row. A table added next year with no
   account column appears in `ORM_ROWS`, not in `ACCOUNT_COLUMN`, and the assertion fails. **This is
   the only property in any of the four options that extends to code nobody has written yet.**

**Enforcing "don't reach around it."** The repo's linter can ban the imports outright, and I verified
this works rather than assuming it. `ruff` already runs `select = ["ALL"]`, which includes the
`flake8-tidy-imports` rules, so no new tool is needed:

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"sqlalchemy.select".msg = "Build queries through the scoped repository."
"sqlalchemy.ext.asyncio.AsyncSession".msg = "Routes and services take a scoped repository."
"app.db.session.build_session_factory".msg = "Sessions are constructed by the lifespan only."

[tool.ruff.lint.per-file-ignores]
"app/db/*" = ["TID251"]
```

> **Executed.** I ran `ruff` 0.16.4 (the version in `server/.venv`) against a throwaway tree outside
> the repository with exactly this configuration. It reported `TID251` for both imports in
> `app/routes/items.py` and exited non-zero; the identical imports in `app/db/repo.py` passed under the
> `per-file-ignores` exemption. The boundary is machine-enforceable with the toolchain already
> configured, and `make check` already runs `ruff check`.

**What it catches.** Every unscoped query written *outside* `app/db/` — which, if the boundary holds,
is every route, every service, and every projection. Both naive forms, not just the `session.get`
one, because neither `select` nor `AsyncSession` is in scope to write them with.

**What it FAILS to catch.**

- **Anything written inside `app/db/`.** The exemption that makes the repository possible is also the
  hole. A contributor adding a method to `ScopedRepository` can write an unscoped `select`, and the
  linter will not object because that file is exempt. The residual risk is real but *bounded to one
  directory* — which is the whole point, and is a different situation from a hole that can appear in
  any file.
- **`# noqa: TID251`.** Lint is advisory to anyone willing to write four characters. It is a control
  against forgetting, not against deciding.
- **Without Option A, the registry is not a registry.** `ACCOUNT_COLUMN` as written above requires
  `OrderItemRow.account_id` to exist. It does not today. Without A, `ScopedRepository._select` cannot
  be one uniform expression; it needs a per-entity join recipe — a hand-written two-level join for
  `return_policies`, `policy_rules` and `return_summaries`. That is still an enormous improvement
  over N hand-written joins scattered across routes, but it means the correctness of isolation rests
  on four bespoke expressions that a reviewer must read carefully, rather than on a dictionary a
  reviewer can check at a glance. **A is what makes B reviewable.**
- **The identity map.** `Session.get()` returns an already-loaded object without emitting SQL. If a
  session ever holds a row from another account, no query-level mechanism — B, C or D — can filter it.
  This argues for a strictly per-request session and for never sharing one across principals; it is
  the one residual that is common to three of the four options.

**Cost.** One new module, a FastAPI dependency, a lifespan-owned engine and session factory (which the
review's `DAL-1` finding requires anyway), and three lines of `pyproject.toml`. No schema change, no
migration, no deployment change.

---

### Option C — PostgreSQL row-level security with a per-request session variable

Enable RLS on every account-owned table; set a session-local variable from the principal at the start
of each request's transaction; let the database refuse to return rows.

```sql
ALTER TABLE return_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE return_summaries FORCE ROW LEVEL SECURITY;

CREATE POLICY return_summaries_account ON return_summaries
    USING (account_id = current_setting('boomerang.account_id', true));
```

```python
await session.execute(
    text("SET LOCAL boomerang.account_id = :account_id"),
    {"account_id": scope.account_id},
)
```

**What it catches — and this is the strongest single property available.** The naive query returns
zero rows. Not an exception, not a wrong answer: nothing. Both forms, `session.get` and
`select().where()`, and equally any `text()` statement, any Core select, any future ORM feature, and
any query written *inside* `app/db/` by someone with commit rights there. It is the only option whose
guarantee does not depend on which Python was written.

Its failure mode is also the best of the four. If the variable is never set,
`current_setting('boomerang.account_id', true)` yields `NULL`, `account_id = NULL` evaluates to `NULL`,
and no row qualifies. A request path that forgets the scope returns nothing at all — loudly, visibly
broken, in development, on the first try.

**What it FAILS to catch, and what it costs.**

- **A table created without `ENABLE ROW LEVEL SECURITY` is completely unprotected, and nothing says
  so.** This is the mirror image of Option B's exhaustiveness check: the new table is silently
  wide open, and the codebase contains no artefact that would notice. Mitigable with a startup or
  test assertion over `pg_class.relrowsecurity`, but that assertion is a thing you must remember to
  write — which is the same class of problem the whole proposal exists to remove.
- **It needs Option A anyway.** A policy on `return_summaries` needs an `account_id` column to
  compare against. Without one, the policy becomes a correlated `EXISTS` subquery walking two levels
  up per row — which is slow on the dashboard's aggregate reads and, more importantly, is a
  hand-written two-level join again, just relocated into DDL where it is harder to review and harder
  to test. **C is not an alternative to A; C is a layer on top of A.**
- **Role separation the current harness actively prevents.** A table's owner bypasses its policies
  unless `FORCE ROW LEVEL SECURITY` is set, and a superuser bypasses them regardless.
  `server/compose.integration.yml` starts PostgreSQL with `POSTGRES_USER: boomerang_test`, which is
  the image's superuser, and `tests/test_db_integration.py` creates the schema over that same
  connection with `Base.metadata.create_all()`. Under that harness, RLS is bypassed and a negative
  test fails. That is a cost, not a silent hole — but it means C cannot be demonstrated at all until
  a non-owner application role is introduced, the schema-creation path is re-homed, and the compose
  file changes.
- **Connection reuse is a cliff, not a slope.** `SET LOCAL` is transaction-scoped; a plain `SET` is
  connection-scoped and survives into the next checkout from the pool. One `SET` where `SET LOCAL`
  was meant, and request *N* reads request *N−1*'s account. The window is invisible under
  single-account tests and under low concurrency, and it is worse behind a connection proxy. The
  mitigation is straightforward — always `SET LOCAL`, always inside a transaction, every read in a
  transaction — but it is discipline again, at a place where the consequence is worse than the bug
  it was hired to fix.
- **Its proof does not run on the gate.** This is the decisive cost in *this* repository. `make check`
  is `fmt-check lint typecheck cov audit`, and the pre-commit hook enforces exactly that.
  PostgreSQL integration tests are a separate opt-in target requiring `TEST_DATABASE_URL` and a
  Docker container. An RLS negative test can only live there. **The strongest mechanism would be the
  one whose test never runs on a commit.** A control nobody is forced to re-prove decays into a
  control nobody notices removing.
- **No migration tooling exists to put the policy DDL in** (section 1.3), and unlike a column
  addition, a policy is invisible in `server/app/db/models.py` — it lives nowhere a Python reader
  looks.

**Cost.** DDL for eight tables plus policies, a second database role, changes to the compose file and
the integration tests, a transaction-per-request discipline, migration tooling adopted first, and a
recurring operational rule that the application never connects as the table owner.

---

### Option D — An ORM-level query filter via `do_orm_execute`

Application-level RLS: a session event handler that injects the account predicate into every ORM
select, keyed off the scope stored on the session.

```python
@event.listens_for(Session, "do_orm_execute")
def _apply_account_scope(state: ORMExecuteState) -> None:
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    account_id = state.session.info.get("account_id")
    if account_id is None:
        msg = "A session with no account scope may not execute an ORM select."
        raise RuntimeError(msg)
    for entity, column in ACCOUNT_COLUMN.items():
        state.statement = state.statement.options(
            with_loader_criteria(entity, column == account_id, include_aliases=True)
        )
```

**What it catches.** Both naive forms, in principle, wherever they are written — including inside
`app/db/` — with no schema privilege change, no second database role, and no migration. It fails
closed on a missing scope by raising. It is testable in the Docker-free suite that gates every commit,
because it operates entirely inside SQLAlchemy. That last property is exactly what Option C lacks, and
it is why D deserves to be scored rather than waved at.

**What it FAILS to catch.**

- Core selects against a `Table`, `session.execute(text(...))`, and anything issued on a raw
  connection. The handler sees ORM executions only.
- Aggregates written as `select(func.count()).select_from(order_items)` rather than over the mapped
  entity — precisely the dashboard-metrics shape from route 2, the one query where the mistake is
  quietest.
- Identity-map hits, as in Option B.
- **It needs `ACCOUNT_COLUMN` to exist, so it also presupposes Option A** — or degenerates into
  per-entity join criteria.

> **Not verified.** Whether `with_loader_criteria` injected through `do_orm_execute` reaches
> `Session.get()` — as opposed to only `select()` executions — is the question that decides whether D
> is a control or a partial control, and I could not run SQLAlchemy here to settle it (section 3,
> Option A). Treat D's coverage of the `session.get` form as unconfirmed.

**Cost.** One module and a session-construction change. Cheap. Its real cost is comprehension: it is
action at a distance. A query that returns fewer rows than its text says it should is the kind of
behaviour that makes a debugging session take a day, and the handler is easy to disable in a
"temporary" diagnostic that then ships.

---

### Set aside

- **An opaque composite handle on the wire** — make the `item_id` a signed token encoding
  `(account_id, item_id)`, so the server never sees a bare item key. Rejected on two grounds: it
  changes a frozen contract field (`design/boomerang-api-contract.md` shows `item_id` as a bare
  opaque identifier and section 2 freezes identifier conventions), and it converts isolation into a
  bearer capability — a leaked handle authorizes access forever, to anyone, which is strictly weaker
  than a predicate evaluated against the current principal.
- **A schema or database per account** — complete isolation, and wildly disproportionate for a
  proof of concept with one retailer and no deployed database. It also makes the account-wide
  dashboard aggregate trivial and everything else, including migrations that do not exist yet, N
  times harder.

---

### Scorecard

Ratings are against the option **alone**, which is why no row is strong everywhere.

| | A: schema threading | B: scoped repository | C: row-level security | D: ORM query filter |
|---|---|---|---|---|
| Kills `session.get(Row, item_id)` | **Yes** — raises deterministically | Yes, outside `app/db/` | **Yes** — zero rows | Unconfirmed |
| Kills `select(Row).where(Row.item_id == id)` | **No** | Yes, outside `app/db/` | **Yes** — zero rows | Yes, for ORM entity selects |
| Protects code inside `app/db/` | Partly | **No** | **Yes** | Yes |
| Catches the dashboard aggregate written over a table | No | Yes, outside `app/db/` | **Yes** | No |
| Extends to a table added next year | Reviewable, not automatic | **Yes** — registry check fails | **No** — new table is silently open | No — absent from the registry |
| Proof runs on every commit | **Yes** — Docker-free | **Yes** — Docker-free | **No** — opt-in integration only | **Yes** — Docker-free |
| Presupposes a schema change | is the schema change | No, but far weaker without A | **Yes** — needs A's columns | **Yes** — needs A's columns |
| Fixes denormalization integrity by construction | **Yes** — composite foreign keys | n/a | n/a | n/a |
| Requires migration tooling that does not exist | Yes | No | Yes | No |
| Requires a second database role | No | No | **Yes** | No |
| New failure mode it introduces | none | none | pooled-connection scope leak | action at a distance |
| Cost | moderate, one-time | low | high | low |

---

## 4. The "fails closed" test

For each option: a contributor joins in four months, has never read this document, is asked to
implement `PUT /v1/items/{item_id}/return-summary`, and writes the obvious thing.

**Today, with no mechanism.** They write `await session.get(ReturnSummaryRow, item_id)`. It compiles.
`mypy --strict` passes — **verified**: the spike in section 3 confirms `Success: no issues found`
against this exact call, because `session.get`'s identifier parameter types to `Any` and cannot be
statically narrowed. `ruff` with every rule enabled passes. The test they write uses one account's
fixtures and passes. Code review sees a primary-key lookup on a table whose primary key is `item_id`
and has nothing to object to. **It works, and it silently reads and overwrites another account's
data.** This is the status quo and it fails open at every gate the project has.

**Option A.** They write the same line. It raises `InvalidRequestError` — **verified** by the spike in
section 3, not merely predicted — not on a cross-account input, on *every* input, including the first
one they try by hand. They look at the model, see a
two-column primary key with `account_id` leading, and either write
`await session.get(ReturnSummaryRow, (account_id, item_id))` or ask where `account_id` comes from.
Both outcomes are correct. **Fails closed for this form, loudly and immediately.** If they instead
reach for `select(ReturnSummaryRow).where(ReturnSummaryRow.item_id == item_id)`, A does not stop
them — but the model file now shows an `account_id` column on the row they are querying, so the
omission is visible to a reviewer reading the same screen. Weaker, and honestly weaker.

**Option B.** They have no `session`. `ruff` rejects `from sqlalchemy import select` and
`from sqlalchemy.ext.asyncio import AsyncSession` in `app/routes/` with the message the ban carries,
and `make check` — which the pre-commit hook runs — blocks the commit. The only thing their handler
can be given is a `ScopedRepository`, whose every method already carries the predicate. **Fails
closed, at commit time, with a message that says what to do instead.** Unless they add the method
inside `app/db/` where the exemption lives, or write `# noqa`.

**Option C.** They write the naive line. It returns `None`. Their happy-path test fails, because a
policy is filtering the row they just inserted under a different scope. They investigate, discover
the session variable, and set it. **Fails closed.** The important caveat is not about them: it is
that the whole thing rests on DDL nobody reads in review, a role separation an operator can undo by
connecting as the owner, and a test that only runs when someone opts into Docker.

**Option D.** The naive `select()` form returns `None` and the same corrective loop as C plays out.
The `session.get` form is unconfirmed. If the handler does not cover it, the answer is "it works and
silently returns another account's data" — and D's score should be read as provisional until that
is settled.

---

## 5. Denormalization integrity

If `account_id` is copied onto `order_items`, `return_policies`, `policy_rules` and
`return_summaries`, something must keep those copies equal to `orders.account_id`. There are three
candidate answers and only one of them is a guarantee.

**Write-path discipline** — every insert sets `account_id` from the same variable used for the order.
Rejected. It is exactly the class of control that produced the finding.

**A trigger** — a `BEFORE INSERT OR UPDATE` trigger that looks up the parent's account and rejects a
mismatch. Works, but lives in DDL nobody reads in review, has no migration home (section 1.3), costs a
per-row lookup on the ingestion write path, and can be disabled per-session by a superuser without
trace.

**Composite foreign keys — recommended.** Because `order_items` references
`orders (account_id, id)` as a unit, and `return_policies`, `policy_rules` and `return_summaries`
reference `order_items (account_id, id)` as a unit, a child row whose `account_id` disagrees with its
parent's **cannot be inserted or updated**. It is not detected after the fact; it is not
representable. There is no reconciliation job, no repair script, no drift.

> **Verified — spike executed 2026-09-13.** PostgreSQL 17.11 (`postgres:17.11-alpine3.24`, the tag
> `server/compose.integration.yml` pins), SQLAlchemy 2.0.52, psycopg 3.3.5. Inserting a child row whose
> `(account_id, order_id)` names a combination absent from the parent is rejected: `IntegrityError`
> wrapping a psycopg `ForeignKeyViolation`, SQLSTATE `23503` — `insert or update on table "child"
> violates foreign key constraint "fk_child_account_order"`, detail `Key (account_id, order_id)=(acct_B,
> order_1) is not present in table "parent".` With the constraint declared **`NOT DEFERRABLE`** (the
> PostgreSQL default), the rejection happens at the INSERT statement itself. Under
> `DEFERRABLE INITIALLY DEFERRED` the identical bad INSERT **succeeds silently**, and the same 23503
> surfaces only at `COMMIT` — a materially later and materially worse failure surface, since a request
> handler that checks its own statement's outcome would see success. **This proposal requires every
> account-scoping composite foreign key be declared `NOT DEFERRABLE` explicitly**, so the guarantee does
> not rest on nobody having reason to change the default.
>
> The spike also confirmed the parent-side unique constraint is not optional. Attempting to create the
> composite foreign key against a parent table that lacks `UNIQUE (account_id, id)` fails at DDL time —
> `ProgrammingError` wrapping psycopg `InvalidForeignKey`, SQLSTATE `42830`, "there is no unique
> constraint matching given keys for referenced table." This confirms `uq_orders_account_id_id` (line
> 265 above) is a hard prerequisite PostgreSQL enforces, not a defensive extra.

The chain holds transitively: every composite foreign key terminates at
`orders (account_id, id)`, and `orders.account_id` is a plain foreign key to `accounts.id`. So a
return summary's account column is equal to its order's account column by referential integrity, all
the way up, at every instant, including mid-transaction.

**What happens if they ever disagree.** They cannot, and the honest form of that answer is: *the only
way to make them disagree is to remove or disable the constraint.* The remaining cases:

- **Changing an order's account.** `UPDATE orders SET account_id = ...` fails with a foreign key
  violation, because the children still point at the old pair — **verified**: PostgreSQL 17.11 rejects
  it under the default `NO ACTION` with SQLSTATE `23503`, "is still referenced from table"; deleting a
  referenced parent is rejected the same way, same SQLSTATE, same message shape. Declare
  **no `ON UPDATE CASCADE`**, and this is not only a principle: the spike built the `ON UPDATE CASCADE`
  variant and ran the identical update against it. It succeeded, and it silently rewrote every child
  row's `account_id` to the new value — a whole subtree of `order_items`, `return_policies`,
  `policy_rules` and `return_summaries` quietly relabelled into another account, with no error, no log
  line, and no row left behind to show it happened. That is the concrete shape of the failure this rule
  exists to prevent. An order never changes accounts; if someone tries, it should fail noisily, not
  quietly relabel the entire subtree.
- **Constraints dropped in a future migration.** Nothing in the database can defend against its own
  DDL. Two cheap backstops: assert the constraint set in the integration suite (the tests already
  build the schema from `Base.metadata`, so the assertion is over metadata and is Docker-free for the
  declarative half), and keep a reconciliation query as a standing integration assertion that must
  always return zero rows:

  ```sql
  SELECT i.id
  FROM order_items i
  JOIN orders o ON i.order_id = o.id
  WHERE i.account_id <> o.account_id;
  ```

  It should never find anything. It exists to document the invariant in executable form and to fail
  the day the constraint is dropped.
- **Bulk loads with constraints disabled.** There is no bulk-load path in this system — the server
  never initiates anything and writes only what the extension sends. If one is ever added, re-enabling
  and revalidating the constraints is part of it.

### 5.1 The account hop this design forbids by construction, not by discipline

Composite foreign keys guarantee that a child's `account_id` agrees with its immediate parent's at
every instant — that is the whole of what section 5 has established so far. They do **not**, by
themselves, guarantee that a row can never be moved onto a *different* parent that happens to share the
child's non-account key. Spike 2 demonstrated this directly: given two `orders` rows `(acct_A, order_1)`
and `(acct_B, order_1)` — the same `order_id`, two different accounts —
`UPDATE child SET account_id = 'acct_B' WHERE item_id = 'item_1'`, leaving `order_id` untouched,
**succeeded**. The child's foreign key was satisfied both before and after the statement; it simply
came to point at a different parent row that happened to share its `order_id`. Nothing was ever
inconsistent, not even mid-transaction. This is a real property of composite foreign keys in general,
and it is the reason a composite key is not, by itself, a hop-proof design — it is worth recording
plainly rather than only implicitly relying on the fact that it does not apply here.

**It is not reachable under this proposal, and the reason is worth stating precisely rather than
asserted.** Two `orders` rows sharing an `order_id` under different accounts is exactly the precondition
the spike's harness allowed, and exactly what this schema forbids. `orders.id` remains a
**single-column** primary key throughout Option A — see the model at line 268 above —
and `UniqueConstraint("account_id", "id", ...)` at line 265 is additive: it does not relax `id`'s own
global uniqueness, and the comment already attached to it says as much ("Not a new uniqueness claim -
id is already unique"). Only the child tables become composite-keyed: `order_items` at lines 286-287,
`return_summaries` at lines 302-303, and `return_policies` / `policy_rules` the same way. Because
`orders.id` is globally unique, no second `orders` row can ever exist with the same `id` under a
different `account_id`, so there is no alternate parent for a child row to be hopped onto. The spike's
harness reproduced the hop only because its `parent` table carried a composite primary key matching its
child — precisely the shape this proposal does not build for `orders`.

**Consequence: `orders.id`'s global uniqueness has changed from a surrogate-key convenience into a
load-bearing invariant of account isolation, and nothing before this amendment recorded that.** State it
as an explicit invariant:

> **Invariant.** `orders.id` MUST remain a single-column primary key, globally unique across all
> accounts. It MUST NOT be widened to a composite `(account_id, id)` primary key, no matter how
> consistent that would look next to its composite-keyed children.

The reason this needs to be written down, rather than left to fall out of "well, that's how Option A
happens to be specified": a future contributor who has read this section and internalized "composite
primary keys enforce account isolation" has every incentive to give `orders` the same treatment as its
children. It would read as fixing an inconsistency. It would pass every test section 7 specifies, since
none of them pins the shape of `orders`'s primary key. And it would silently open exactly the hop
described above, because `orders.id`'s single-column global uniqueness is the one precondition this
proposal currently relies on without asserting it anywhere in code.

**The test that must exist because of this.** Section 7.4 already specifies a test asserting
`ReturnSummaryRow`'s primary-key shape and order; this invariant needs the same treatment on the *other*
end of the chain, on `orders`, or the guard in section 7.4 stays silent about the one change that would
defeat it:

```python
def test_orders_primary_key_is_single_column_and_globally_unique() -> None:
    """orders.id anchors account isolation; see design/boomerang-account-scoping.md section 5.1.

    If this fails, two accounts can share an order_id, and a composite-keyed child can be UPDATEd
    from one account to another with its foreign key satisfied throughout.
    """
    pk_columns = [column.name for column in inspect(OrderRow).primary_key]
    assert pk_columns == ["id"]
```

This test fails the day someone gives `orders` a composite `(account_id, id)` primary key — which is
exactly the day the hop stops being theoretical. It belongs in `server/tests/test_db_models.py` alongside
the primary-key-shape assertions section 7.4 already specifies for the child tables, and it is, on
balance, the single most valuable addition this amendment makes: everything else here confirms a
prediction; this names a risk nobody had written down.

### 5.2 `MATCH SIMPLE`, `NULL`, and why every participating column must be `NOT NULL`

PostgreSQL's default match semantics, `MATCH SIMPLE`, skip the foreign-key check entirely on any row
where **any one** of the composite key's columns is `NULL` — the whole row is exempted, not just the
null column. Spike 2 confirmed this directly: a child row with `account_id = 'does_not_exist'` — a real,
non-matching value — and `order_id = NULL` **inserted successfully**, because one column of the pair
was `NULL` and `MATCH SIMPLE` does not check a partially-null key at all. Under `MATCH FULL`, that same
mixed case is correctly rejected — `IntegrityError`, SQLSTATE `23503`, "MATCH FULL does not allow mixing
of null and nonnull key values" — while a fully-`NULL` pair, `(NULL, NULL)`, is still permitted under
`MATCH FULL`, as the standard requires.

This means `MATCH SIMPLE` is only as strong as "every participating column is `NOT NULL`." If it is not,
a caller — or a bug — can construct a row that names a real, wrong account and slips past the foreign
key entirely by leaving the other key column unset. **The current schema already avoids this, but by
inference rather than by a stated rule.** `order_items.order_id` is declared `Mapped[str]`, not
`Mapped[str | None]`, at `server/app/db/models.py:154`, so SQLAlchemy renders it `NOT NULL`, and the
escape this section describes cannot occur today. I checked the same for every other column that would
participate in an account-scoping composite foreign key: `return_policies.item_id`
(`server/app/db/models.py:217`), `policy_rules.item_id` (`server/app/db/models.py:248`) and
`policy_rules.id` (`server/app/db/models.py:252`), and `return_summaries.item_id`
(`server/app/db/models.py:309`) are each declared `Mapped[str]` — none is nullable. None of the four
tables this proposal touches needs a nullability change on its existing columns.

**Require, explicitly:** every column participating in an account-scoping composite foreign key — the
new `account_id` columns this proposal adds to `order_items`, `return_policies`, `policy_rules` and
`return_summaries`, and their existing partner columns `order_id` / `item_id` / `id` named above — is
`NOT NULL` (automatic for all of these under Option A, since every one is a primary-key column, but
worth stating as a requirement rather than a byproduct). **Recommend, as defence in depth: declare every
one of these foreign keys `MATCH FULL`.** `MATCH SIMPLE`'s current safety is a fact that happens to be
true because these columns are already `NOT NULL`; `MATCH FULL` makes that safety a property of the
constraint itself, so it does not depend on a reviewer re-confirming, forever, that no future migration
ever makes one of these columns nullable.

---

## 6. Indistinguishable from not-found

The contract states it twice: section 3.2, "An item identifier belonging to another account returns
`404 not_found`, not `403`, so the API does not reveal cross-account existence"; and section 14, first
required test. The data model repeats it in its relationships section. Two of the seven routes take a
caller-supplied identifier and must satisfy it: `GET /v1/items/{item_id}` and
`PUT /v1/items/{item_id}/return-summary`.

### 6.1 The anti-pattern that must be forbidden by name

```python
# Forbidden. This is distinguishable, and it is what people write.
row = await repo.get_unscoped(ReturnSummaryRow, item_id)
if row is None or row.account_id != scope.account_id:
    raise NotFound
```

It produces the right status code and the wrong timing. The cross-account request performs a
successful index lookup, materializes a row, and on the detail route may go on to load the item, its
order, its policy and its rules before the check fires — while the genuinely-absent request does an
index probe that finds nothing and stops. The difference is real work on real data and it is
measurable in aggregate over enough requests. The contract says "not a different response time in any
way the caller can observe," and this pattern is exactly that.

**The rule: scoping is a predicate, never a comparison.** The account is part of the question asked of
the database, not part of the answer checked afterwards. Under the recommendation this is not a rule
anyone has to follow, because `ScopedRepository` exposes no unscoped fetch to build the anti-pattern
out of.

### 6.2 What the recommendation actually emits

```sql
SELECT ... FROM return_summaries WHERE account_id = $1 AND item_id = $2;
```

A probe of the composite primary-key index. A cross-account item and a fabricated item are the same
probe against the same index, both finding nothing, both returning zero rows, both taking the same
branch in the handler, both raising the same exception, both rendered by the same handler. The only
physical difference is which index page is touched, which is not observable over HTTP.

Applied per route:

**`GET /v1/items/{item_id}`.** The scoped fetch returns `None` for both cases. The handler raises
before it loads the order, the policy, the rules or the summary — so the cross-account request does
strictly less work than a successful one, and exactly as much as an absent one.

**`PUT /v1/items/{item_id}/return-summary`.** Order of operations is part of the requirement:

1. FastAPI validates the body → `422 validation_failed` on a malformed body. This happens before the
   handler and therefore before the scope check. It reveals nothing about the item, because it is a
   statement about the body; a caller learns the same thing sending a bad body with a fabricated id.
   This is acceptable and unavoidable.
2. Resolve the summary through the scoped repository. `None` → `404 not_found`.
3. Only then validate the transition → `409 state_transition_not_allowed`.
4. Only then check the blocked states → `409 state_blocked`.

Inverting 2 and 3 leaks existence *and* state, since only some current states produce that `409`.
Section 7 specifies the test for this ordering, because it is the failure most likely to be
introduced later by someone refactoring the validator into a decorator or a dependency.

### 6.3 What "byte-identical" means precisely

The error body carries `request_id`, which differs on every request by design
(`server/AGENTS.md`, error shape: "`request_id` goes on **every** response"). So the requirement is:

- identical status: `404`;
- identical headers, including `Cache-Control: private, no-store`;
- identical `reason`: `not_found`;
- identical `message` — one constant string, never interpolating the identifier or anything about it;
- identical `details`: **`null`**, never a field list naming what was rejected;
- `request_id` the only differing field, and differing on two absent-item requests too.

Both cases must also travel the same exception class through the same handler. If cross-account
raises one exception type and absence raises another, the two bodies are identical today and free to
drift tomorrow — one `NotFound`, one handler, one message constant.

---

## 7. Testability

The review's `DAL-2` finding asks for a test that enumerates every item-addressed route rather than
testing isolation once, and the brief asks whether the mechanism admits a test that fails if the
mechanism is removed. Both are answerable, and the second is the harder and more valuable one.

**First, the trap.** A single-account fixture cannot detect this defect. Every query — scoped or
unscoped — returns the right rows when only one account exists. **Every test relevant to isolation
requires at least two populated accounts, and the second account's data must be non-empty and must
overlap in shape with the first.** A second account with no items proves nothing.

### 7.1 The negative test

A second account owns a complete graph: an order, an item, a policy with rules, and a summary. The
first account is authenticated. For each item-addressed route, assert the cross-account response
equals the fabricated-identifier response under the section 6.3 comparison — status, headers, and body
with `request_id` normalized.

The route list is **data, not prose**: a module-level table of `(method, path_template, body_factory)`
that the test parametrizes over. A companion test compares that table against the paths actually
registered on the FastAPI app, so a route added later that takes an identifier and is not in the table
fails the suite. That is what makes it an enumeration rather than a sample.

### 7.2 The ordering test

Give the second account's item a current state from which the requested transition is illegal, then
issue the write as the first account. Assert `404`, not `409`. Without it, an ownership check
refactored behind a transition validator breaks the contract while every other test still passes.

### 7.3 The write test

Route 6 is the only write. After a rejected cross-account publication, assert the second account's
summary row is byte-for-byte unchanged — state, `update_source`, `handoff_evidence`, `observed_at`
and `updated_at`. A `404` that has already performed the write is not isolation.

### 7.4 Tests that fail if the mechanism is removed

This is the part that distinguishes a mechanism from a convention. Each of these is Docker-free, runs
under `make check`, and counts toward the coverage floor.

| Removal | What fails |
|---|---|
| `account_id` dropped from a row | The registry assertion: `unscoped_rows(ACCOUNT_COLUMN) == frozenset()`. |
| A new table added with no account column | The same assertion — **without anyone remembering to update the test.** |
| The composite primary key reverted to `item_id` alone | A test asserting `inspect(ReturnSummaryRow).primary_key` column names and their order. |
| The scoped repository bypassed in a route | A boundary test that walks the AST of every module under `app/routes/` and `app/services/` and asserts none imports `sqlalchemy`, `sqlalchemy.ext.asyncio` or `app.db.session`. |
| The lint ban removed from `pyproject.toml` | A test asserting the banned-api keys are present in the parsed config. |
| A composite foreign key dropped | An integration test asserting the constraint set, plus the zero-row reconciliation query from section 5. |

The composite-foreign-key rejection test — insert an `order_items` row whose `account_id` disagrees
with its order's, assert `IntegrityError` — needs real PostgreSQL and therefore lives in the opt-in
integration suite. That is acceptable *because* it is the belt to the recommendation's braces; the
braces (registry, primary-key shape, boundary, lint config) all run on the gate.

### 7.5 Interaction with the coverage floor

`server/pyproject.toml` sets `fail_under = 95` with `branch = true` and `source = ["app"]`; the
workspace guide records the current figure as 100% on both. The recommended code adds perhaps 120
lines across `app/db/scope.py` and a dependency provider, most of it branch-free, so reaching the
floor is straightforward and the tests above supply the branches that exist.

Two honest warnings.

First, **the coverage floor is not a scoping control and must not be reported as one.** A repository
with 100% line and branch coverage can be missing a predicate on every method; coverage measures
whether a line ran, not whether the query was right. The only artefacts in section 7.4 that prove
scoping are the two-account negative test and the registry assertion.

Second, the exhaustiveness guard should be written as a **function plus a test**, not as a
module-level `raise`:

```python
def unscoped_rows(
    registry: Mapping[type[Base], InstrumentedAttribute[str]],
) -> frozenset[type[Base]]:
    """Return every stored row that declares no account column."""
    return frozenset(ORM_ROWS) - frozenset(registry) - {AccountRow}
```

A module-level `if ...: raise` that is never true is a permanently missed branch, and the only ways
out are a `# pragma: no cover` — which the workspace guide restricts to genuinely unreachable lines
with a stated reason — or an import-time failure injection test. As a pure function it takes two
tests: the real registry returns empty, and a deliberately incomplete one returns the missing rows.
Both branches covered, no pragma, and the guard still fails the commit on the day someone adds a
table without an account column.

---

## 8. Migration

### 8.1 What migration actually means here

Section 1.3 and section 1.4 established two things the brief assumed otherwise: **there is no
migration tooling in this repository**, and **there is no deployed database and no persisted row.**
The schema exists as Python declarations in `server/app/db/models.py` and is instantiated only by
`Base.metadata.create_all()` inside the opt-in integration tests, against a container whose data
directory is `tmpfs`.

So the migration for Option A is: **edit the model file, edit the mappers, edit the tests, run
`make check` and `make integration`.** There is no backfill, no dual-write window, no cutover, and
no downtime, because there is nothing running to take down. This is the cheapest moment this change
will ever have, and every week of ingestion work makes it more expensive.

### 8.2 Adopt migration tooling in the same change

Not because this change needs it, but because the next one will and this is the last moment adding it
is free. The review's `DAL-5` finding already recommends decoupling migrations from the retention
blocker and adopting a tool at the first persisted table. The recommended sequence:

1. Add the migration dependency through `uv` — `uv add`, never `pip`, never `requirements.txt`, per
   `server/AGENTS.md`.
2. Generate an initial revision capturing the schema **as recommended here**, so the composite keys
   and composite foreign keys are the baseline rather than a later alteration. A project with no
   migration history gets exactly one chance at a clean baseline.
3. Add a `make migrate` target alongside the existing gates.
4. Leave `create_all()` in the integration tests. The workspace guide is explicit that schema
   lifecycle is observable there on purpose, and it is a genuine cross-check: if `create_all()` and
   the migration history ever produce different schemas, one of them is wrong, and a test comparing
   the two catches it.

Note that this proposal touches none of the six native PostgreSQL enum types. The enum-versus-text
question `DAL-5` raises is neither helped nor worsened here and remains open on its own terms.

### 8.3 If a deployed database existed — the online sequence

Recorded for completeness, and because it should be read before anyone concludes the change stays
free after deployment.

| Step | Online? |
|---|---|
| Add `account_id` as nullable to the four tables | Yes — a nullable column with no default is metadata-only. |
| Backfill from `orders` in batches | Yes. |
| `SET NOT NULL` | Yes via a `NOT VALID` check constraint, `VALIDATE`, then attach — a full-table scan otherwise. |
| Add `UNIQUE (account_id, id)` on `orders` | Yes, with `CREATE UNIQUE INDEX CONCURRENTLY` then `ADD CONSTRAINT ... USING INDEX`. |
| Add the composite foreign keys | Yes, as `NOT VALID`, then `VALIDATE CONSTRAINT` under a share lock. |
| **Swap the primary keys** | **No — this is the one step with a real lock.** Build the new unique index `CONCURRENTLY`, then attach it as the primary key under a brief `ACCESS EXCLUSIVE` lock while dropping the old one. Short, but a lock. |
| Drop the redundant single-column foreign keys and `ix_orders_account_id` | Yes. |

Application code must tolerate both shapes across the window, which in practice means the repository
lands before the primary-key swap and the swap happens last. **None of this applies today.** Doing
the change now costs one file edit; deferring it past a deployment costs the table above plus a
maintenance window.

---

## 9. Recommendation

**Adopt Option A and Option B together, now, as one change. Treat Option C as the follow-on that
Option A makes cheap, adopted once migration tooling and a non-owner application role exist. Reject
Option D.**

Neither A nor B is sufficient alone, and the reason they are recommended as a pair is not "belt and
braces" — it is that each one repairs the other's central weakness.

- **A alone** kills the shortest unsafe form and leaves `select().where()` open. It is a schema, and
  a schema cannot complete a predicate someone wrote by hand.
- **B alone** covers every query outside `app/db/`, but without A its scoping predicate for
  `return_policies`, `policy_rules` and `return_summaries` is four bespoke two-level joins that a
  reviewer must read line by line. A reduces each to one column equality and turns the whole thing
  into a dictionary that can be checked at a glance and asserted exhaustively.
- **Together**, the naive query at the route layer does not compile — `select` and `AsyncSession` are
  not importable there and the linter blocks the commit — and the naive by-key lookup does not run
  anywhere, because the identity arity is wrong. What remains reachable is a hand-written unscoped
  `select()` **inside `app/db/`**, by someone with commit rights to the one directory whose entire
  purpose is this predicate. That is the residual risk, stated plainly, and it is the residual that
  Option C later removes.

**The decisive reason** is section 3's last scorecard row, and it is specific to this repository
rather than general advice. Option C is the strongest mechanism on paper — it is the only one where
the naive query returns nothing regardless of what Python was written. But its proof can only live in
the opt-in PostgreSQL integration suite, which is not part of `make check` and not part of the
pre-commit hook, while A's and B's proofs — primary-key shape, registry exhaustiveness, the AST
boundary walk, the lint configuration, the two-account negative test — all run Docker-free on every
commit. **In a project that gates hard on `make check` and enforces a 95% floor there, a mechanism
whose proof does not run on the gate is a mechanism that will be removed by accident and noticed by
nobody.** A and B are weaker in the abstract and stronger in practice, because they are continuously
re-proven.

The secondary reason is section 5. Composite foreign keys make the denormalized column's consistency
a referential-integrity guarantee rather than a discipline, a trigger or a reconciliation job. Every
other denormalization strategy answers "what if they disagree" with a detection mechanism. This one
answers it with "they cannot."

Option D is rejected for two reasons: its coverage of the `session.get` form is unconfirmed
(section 3, Option D), and it is action at a distance — a query that silently returns fewer rows than
its text says. Where D would apply, C does the same job in the database with a better failure mode
and no ambiguity about which statements it reaches. If the RLS role separation ever proves impossible
in the eventual deployment topology, D is the right fallback and should be re-scored then, starting
with the spike.

---

## 10. What would have to change to adopt this

Every file and document that moves. The recommendation was accepted on 2026-09-13; this list is
therefore the outstanding work, not a hypothetical. Nothing in it has been modified by this
document, with one exception: the `plan/boomerang-decisions.md` row below is done — the decision is
registered there as `MIG-16`.

### Server code

| Path | Change |
|---|---|
| `server/app/db/models.py` | Add `account_id` to `OrderItemRow`, `ReturnPolicyRow`, `PolicyRuleRow`, `ReturnSummaryRow` as the leading primary-key column, `NOT NULL` (automatic as a primary-key column). Add `UniqueConstraint("account_id", "id")` to `OrderRow` and `UniqueConstraint("id")` to `OrderItemRow`. Replace the four single-column foreign keys with composite `ForeignKeyConstraint`s, each explicitly named, each declared `NOT DEFERRABLE` and `MATCH FULL` (section 5, section 5.2). Leave `OrderRow.id` a single-column primary key — do not widen it to `(account_id, id)` (section 5.1). Add `Index("ix_order_items_account_id_order_id", ...)`. Remove `ix_orders_account_id` (line 111) as redundant, and reconsider `ix_order_items_order_id` (line 150) once every read carries the account. |
| `server/app/db/scope.py` | **New.** `AccountScope`, `ACCOUNT_COLUMN`, `unscoped_rows`, `ScopedRepository`. |
| `server/app/db/mappers.py` | `order_item_to_row`, `return_policy_to_row` and `return_summary_to_row` take the account as a first argument. `_policy_rule_to_row(item_id, rule)` at line 109 is the existing precedent for threading a key through a mapper. The `*_from_row` direction is unchanged. |
| `server/app/db/session.py` | No change in shape. It becomes importable only from `app/db/` under the lint ban, and gains the lifespan caller the review's `DAL-1` finding requires. |
| `server/app/main.py` | Construct and dispose the engine and session factory in the lifespan; add the per-request session and `ScopedRepository` dependency. Required by `DAL-1` regardless of this proposal. |
| `server/app/routes/`, `server/app/api/` | Currently one line each. Handlers, when written, take `ScopedRepository` and never `AsyncSession`. |
| `server/pyproject.toml` | Add `[tool.ruff.lint.flake8-tidy-imports.banned-api]` and the `"app/db/*" = ["TID251"]` per-file-ignore. Add the migration dependency if section 8.2 is taken in the same change. No coverage-config change. |
| `server/Makefile` | A `migrate` target, if section 8.2 is taken. |

### Server tests

| Path | Change |
|---|---|
| `server/tests/test_db_models.py` | Assert primary-key shape and order per row, **including that `OrderRow`'s primary key stays single-column (section 5.1)**; assert the composite foreign-key targets. |
| `server/tests/test_db_mappers.py` | Updated for the new mapper signatures. |
| `server/tests/test_db_scope.py` | **New.** Registry exhaustiveness both ways; `ScopedRepository` predicate construction. |
| `server/tests/test_boundary.py` | **New.** AST walk asserting no module under `app/routes/` or `app/services/` imports a session or `select`; assert the banned-api keys are present in `pyproject.toml`. |
| `server/tests/test_routes_account_isolation.py` | **New.** The two-account parametrized negative test, the route-table exhaustiveness check, the ordering test, and the write-rejection test. |
| `server/tests/test_db_integration.py` | Second account in the graph fixture; composite foreign-key rejection; the zero-row reconciliation query. |

### Design documents

| Path | Change |
|---|---|
| `design/boomerang-low-level-design.md` | Section 2.3's persistence-layer row ("Own database transactions and account scoping") names the device. Section 2.4 stops deferring index and constraint decisions — see the conflict in section 12. Section 10's verification strategy gains the per-route negative test. |
| `design/boomerang-data-model.md` | Section 9's ownership sentence becomes a statement about a constraint rather than a property. Section 11 already permits ORM table layout to diverge from the logical model, so it is the licence for this change and needs no edit. |
| `design/boomerang-api-contract.md` | **No change.** `item_id` stays a bare opaque identifier; section 3.2 and the first required test in section 14 already state what this proposal implements. That the frozen contract is untouched is a property of the recommendation, not a coincidence. |
| `plan/boomerang-decisions.md` | A decision entry if accepted. Note `PROV-03` currently defers database, ORM, migration, index and lifecycle selection consistently with the retention blocker. |
| `plan/tasks/` | A task file, ordered before any route work. |
| `reviews/boomerang-low-level-design-review-2026-09-13.md` | Not edited by this proposal. `DAL-2` is resolved by acceptance, not by amendment. |

### Not changed

`client/`, `infra/`, the unbuilt extension workspace, `.github/`, `docs/`, and every other design
document.

---

## 11. Interaction with the auth decision

**This recommendation is independent of how extension-to-server authentication resolves, and can
proceed in parallel.**

It depends on exactly one property of whatever authentication lands: that the authentication boundary
produces a server-side account identifier that is never read from a request body, path segment or
query parameter. That property is already frozen in the accepted contract — section 3.2 states the
server maps the principal to an account using the Google `sub` claim and that "Clients never submit an
`account_id` to choose the account being accessed." It is a precondition this proposal consumes, not
one it asks anyone to decide.

Every option in `design/boomerang-extension-auth-proposal.md` satisfied it identically, and the
option accepted on 2026-09-13 — server-brokered browser linking, with a bearer credential on the
extension leg and a first-party cookie on the dashboard leg — satisfies it too. Two transports, one
account principal, resolved server-side; that resolution is the one line of `AccountScope`. The
mechanism recommended here is downstream of that line and sees nothing above it.

One detail of the accepted scheme is worth carrying into the coupling below: the principal now also
carries a **client kind**, because the wire contract makes summary publication extension-only and
account deletion dashboard-only. Client kind is a separate axis from the account and must not be
folded into `AccountScope`, whose single job is the account predicate.

Two couplings are worth stating so they are not discovered later:

1. **`AccountScope.account_id` must never become optional.** If authentication later introduces a
   service principal, a health-check caller, or an operational path with no single account, the
   temptation will be to widen the type to `str | None` and branch. That converts a mechanism into a
   convention in a single diff. The correct move is a separate, differently-named unscoped repository
   with its own review and its own tests, so that "this query is not account-scoped" is a visible
   decision rather than a nullable field.
2. **The type must be produced only by the authentication boundary.** The review's `CLASS-2` finding
   asks for exactly this — one principal type, never deserialized from a request body, as the first
   parameter of every account-scoped call. `AccountScope` is a candidate for that type, and if the
   authentication work defines its own principal type first, `AccountScope` should be derived from it
   rather than duplicating it. That is a naming coordination, not a dependency. With both decisions
   now accepted, the coordination is live: the authentication boundary produces a principal carrying
   an account and a client kind, and `AccountScope` is the account half of it.

The reverse direction is also clear: nothing in this proposal constrains the authentication decision.
It adds no requirement about session transport, credential lifetime, cross-origin behaviour or the
Google exchange route, and the accepted authentication design adds none back.

---

## 12. Where this proposal conflicts with what is already written

Stated plainly so the conflicts can be surfaced rather than discovered during implementation.

1. **The brief's premise about migration tooling is wrong.** There is no Alembic and no migration
   library of any kind (section 1.3). The review's `DAL-5` finding says the same independently.
2. **The brief's premise about data-bearing tables is wrong.** No deployed database exists; the only
   PostgreSQL is `tmpfs`-backed and disposable (section 1.4). This makes the recommendation cheaper,
   not harder.
3. **`design/boomerang-low-level-design.md` section 2.4 conflicts directly.** It states that physical
   database selection, migrations, indexes, backup topology and retention "should be designed after
   `ARCH-B4` is resolved sufficiently to define their lifecycle." This proposal requires primary-key,
   constraint and index decisions **now**. That conflict is not created here — the review's `DAL-5`
   finding already observes that the blocker is about record lifetimes while the schema is being
   written today, and eight tables with six native enum types are already committed under that
   deferral. Accepting this proposal means accepting that the deferral in section 2.4 has already
   lapsed in practice.
4. **`design/boomerang-data-model.md` section 11 is the licence, not a conflict.** It states that
   "ORM names, table layout, and internal identifiers do not need to match this document," which is
   what permits denormalizing an account column that the logical model does not carry.
5. **The domain records are a fork that must be chosen deliberately.** `OrderItem`
   (`server/app/models/domain.py:160-164`), `ReturnPolicy` (`:183-186`) and `ReturnSummary`
   (`:220-223`) carry no `account_id`, and neither does the accepted data model. Passing the account
   as a mapper argument keeps both aligned and is what section 10 recommends. Adding `account_id` to
   the domain records instead **would contradict the accepted data model** and should not be done as
   a side effect of this change.
6. **`server/AGENTS.md` states that future routes and services must not return ORM rows directly.**
   Consistent with this proposal — `ScopedRepository` returns rows, and the mappers convert at the
   service boundary as they already do — but worth noting because a repository is the layer where
   that rule is most often broken.
7. **`lazy="raise"` cuts both ways.** It means the recommended scoped reads must eager-load
   explicitly, which the review's `DAL-6` finding already raises as unspecified for the dashboard.
   This proposal does not resolve the eager-loading strategy; it only ensures that whatever strategy
   is chosen starts from a scoped statement.

---

## 13. What this proposal does not decide

Deliberately out of scope, so acceptance is not read as closing them:

- **The dashboard read shape** — one query or two, aggregation in SQL or in Python, eager-loading
  strategy, pagination and the enumerated sort and filter vocabulary. The review's `DAL-6` finding
  owns this. This proposal only requires that the account-wide metric query carry the same predicate
  as the candidate query, which is what makes forgetting it a filter bug instead of a disclosure.
- **The account deletion path** — order of operations, database cascade versus application cascade,
  and completeness verification. The review's `DAL-4` finding owns it. The recommendation helps by
  giving every row an account column to delete by and a composite key that cannot address another
  account's row, but it does not specify the cascade.
- **Identifier minting** — who mints order and item identifiers and whether normalization output can
  influence record identity. The review's `DAL-3` finding owns it, and section 2.5 explains why it
  changes the severity of this finding rather than its shape.
- **Rescan identity and the nullable-reference duplicate** — also `DAL-3`.
- **The transaction boundary and session lifecycle** — `DAL-1`. The recommendation assumes a
  per-request session, which is also what the identity-map residual in section 3 requires, but it
  does not specify where transactions begin and end.
- **Whether closed vocabularies stay native PostgreSQL enums or become constrained text** — `DAL-5`,
  untouched here.
