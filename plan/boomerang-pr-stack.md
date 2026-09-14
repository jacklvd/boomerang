# Splitting the current working tree into a stacked PR series

Status: **plan only.** Nothing in this document has been executed. No branch was created, nothing
was staged, nothing was committed. Verified 2026-09-13 against the working tree as it stood at that
moment — see the caveat in §0.3, three agents were still writing to `server/` while this was written.

> **Six-branch shape, chosen under deadline.** This document originally specified a nine-PR stack
> (§6.5's recommendation). Under time pressure, the user chose a six-branch shape instead, taking
> all three of the sanctioned collapses in §6.4 — fold PR 3 into PR 4, fold PR 7 into PR 8, and fold
> PR 5 into PR 4, in the original nine-PR numbering — and stopping short of the two collapses §6.4
> rules out (folding PR 8 into PR 9, and folding PR 6 into anything). The rest of this document has
> been rewritten around that six-branch shape. Where the original nine-PR reasoning is still the
> right way to explain a tradeoff — §6.4 and §6.5 in particular — it is kept and annotated against
> the original numbering, so a future reader can see this was a deliberate trade under deadline, not
> the shape this plan actually recommended.

---

## 0. The verified starting state

### 0.1 There is no history to rewrite

```
$ git status -sb
## feature/backend

$ git rev-list --left-right --count origin/main...HEAD
0	0

$ git rev-parse HEAD
fa6339f0902bb8c8d9359e083c9c4d0c7a0c479c
$ git rev-parse origin/main
fa6339f0902bb8c8d9359e083c9c4d0c7a0c479c
```

`feature/backend` is **zero commits ahead and zero behind `origin/main`**, sitting exactly on
`fa6339f` ("Dashboard — returns and carrier-neutral pickups (#11)"). The branch has never been
committed to. Every change described below exists only as modified tracked files and untracked new
files in the working tree.

This is the good case. There is no rebase, no `filter-branch`, no commit surgery. The task is to
walk the working tree forward through a sequence of branches, staging a chosen subset at each step.

### 0.2 Full inventory

**Modified tracked files** (`git diff --stat`, 12 files, +1516 / −161):

| File | Δ lines | Belongs to |
|---|---:|---|
| `design/boomerang-api-contract.md` | 356 | branch 2 |
| `infra/AGENTS.md` | 156 | branch 2 |
| `plan/boomerang-decisions.md` | 90 | branch 2 |
| `server/app/db/mappers.py` | 15 | branch 3 |
| `server/app/db/models.py` | 418 | **branch 3** |
| `server/app/main.py` | 26 | branch 5 |
| `server/app/routes/__init__.py` | 22 | **branch 5 + branch 6** |
| `server/pyproject.toml` | 10 | branch 4 |
| `server/tests/conftest.py` | 69 | branch 5 |
| `server/tests/test_db_integration.py` | 340 | **branch 3** |
| `server/tests/test_db_mappers.py` | 8 | branch 3 |
| `server/tests/test_db_models.py` | 167 | **branch 3** |

**Untracked files** (20 files, 8997+ lines — see note below on this document's own line count):

| File | Lines | Belongs to |
|---|---:|---|
| `.github/workflows/server.yml` | 101 | branch 1 |
| `design/boomerang-account-scoping.md` | 1327 | branch 2 |
| `design/boomerang-auth-open-decisions.md` | 550 | branch 2 |
| `design/boomerang-deployment-topology.md` | 522 | branch 2 |
| `design/boomerang-extension-auth-proposal.md` | 860 | branch 2 |
| `design/boomerang-pairing-persistence.md` | 1028 | branch 2 |
| `plan/boomerang-pr-stack.md` | ~1380 | branch 2 |
| `reviews/boomerang-high-level-design-review-2026-09-13.md` | 518 | branch 2 |
| `reviews/boomerang-low-level-design-review-2026-09-13.md` | 735 | branch 2 |
| `server/app/api/auth.py` | 107 | branch 5 |
| `server/app/api/deps.py` | 147 | branch 5 |
| `server/app/api/errors.py` | 269 | branch 5 |
| `server/app/db/repository.py` | 344 | branch 4 |
| `server/app/routes/items.py` | 294 | branch 6 |
| `server/app/routes/me.py` | 49 | branch 5 |
| `server/tests/test_auth.py` | 148 | branch 5 |
| `server/tests/test_errors.py` | 212 | branch 5 |
| `server/tests/test_repository.py` | 831 | branch 4 |
| `server/tests/test_routes_items.py` | 635 | branch 6 |
| `server/tests/test_routes_me.py` | 420 | branch 5 |

Note `server/app/api/__init__.py` already exists on `main` and is not part of this work.

**This document itself is in the inventory.** `plan/boomerang-pr-stack.md` is untracked, exactly like
the nineteen files above it, and it never stages itself — an earlier version of this plan omitted it
entirely, which meant the final `git status --porcelain` check in §7 could never actually come back
empty. `plan/boomerang-decisions.md` already ships in branch 2 alongside the other design and planning
prose, and this document is planning prose about the same work, so it ships there too rather than
getting a branch of its own or being left uncommitted on purpose. Its own line count moves every time
it is edited, which is why the table above gives it an approximate figure rather than a fixed one —
recompute with `wc -l plan/boomerang-pr-stack.md` immediately before execution and use that number in
the branch 2 commit message if it matters enough to state precisely.

### 0.3 Work that has not landed yet

Three agents were writing to the tree while this plan was produced. **Do not begin execution until
they have all finished.** The files they own are:

- `server/app/routes/items.py` (and `server/tests/test_routes_items.py`) — branch 6
- `server/app/routes/__init__.py` — branch 5 and branch 6
- `server/app/db/repository.py` (and `server/tests/test_repository.py`) — branch 4

What this plan depends on and cannot verify:

1. **Branch 4's coverage.** `server/app/db/repository.py` is 344 lines and its only non-integration
   coverage is `server/tests/test_repository.py` lines 1–470 (tests from line 471 onward carry
   `@pytest.mark.integration`, which `make cov` excludes — see §5.1). Whether those tests reach
   `fail_under = 95` on a file still being written is not knowable from here. This is the single
   highest-risk boundary in the stack.
2. **Branch 6's shape.** `items.py`'s public surface is currently one route (`GET /items/{item_id}`).
   If the in-flight agent adds a second, branch 6 grows but its boundary does not move.
3. **Branch 5 / branch 6's shared file.** `server/app/routes/__init__.py` currently imports *both*
   `me` and `items`. That file must be hand-authored at an intermediate state for branch 5 — see §4.

Re-verify §0.1 and §0.2 immediately before executing. If any of it has changed, re-derive; do not
execute a stale plan.

---

## 1. The stack

Six branches. Each is based on the one before it. Ordering is driven by dependency (schema before the
code that queries it; error envelope and auth seam before the routes that raise through them) and,
where dependency leaves a choice, by reviewability. This is the six-branch shape reached by taking all
three sanctioned collapses in §6.4 against the original nine-PR plan — see the note at the top of
this document.

```
origin/main
 └─ 1. ci/server-workflow                  .github/workflows/server.yml
     └─ 2. docs/auth-and-scoping-design    design/, reviews/, plan/, infra/
         └─ 3. feat/account-scoped-composite-keys
             └─ 4. feat/scoped-repository
                 └─ 5. feat/http-layer-and-me-route
                     └─ 6. feat/v1-item-detail-route
```

---

### PR 1 — `ci/server-workflow`

**Title:** run the server's quality gate on every pull request

**Base:** `origin/main`

**Contents (whole-file, 1 file, +101):**
- `.github/workflows/server.yml` *(new)*

**What a reviewer is asked to judge.** Whether the GitHub Actions workflow is a faithful mirror of
what `make check` and `scripts/pre-commit-server.sh` already enforce locally: the same six gates in
the same order, the audit step advisory-only exactly as the hook has it, the integration job pinned
to the same `postgres:17.11-alpine3.24` image and the same credentials as
`server/compose.integration.yml`, and path filters that keep client/docs/design/plan changes from
burning minutes. It is 101 lines of YAML with no application code in it, and it is the only PR in
this stack a reviewer can fully judge without reading any Python.

**Staging:** whole-file.

**Green?** Yes. The workflow's `paths` filter includes `.github/workflows/server.yml` itself, so
this PR triggers its own run — against `origin/main`'s tree, which is the last merged, hook-gated,
100%-coverage state. `make fmt-check`, `make lint`, `make typecheck`, `make cov` all pass there
because they passed when `#11` merged.

**Why the workflow goes first.** The alternative — land it last, once the tree it checks is
complete — gets the ordering exactly backwards. Landing it first means branches 2 through 6 are each
gated by the real CI, on the real runner, against the real PostgreSQL service, rather than on a
reviewer trusting five separate "I ran `make check` locally" claims. The objection ("CI must pass
against a tree that does not yet contain the work") is not actually a cost here: the tree it runs
against is `main`, `main` is green, and a CI workflow that only proves itself once the feature lands
has proved nothing at the moment you most needed it. The one genuine risk is that the workflow is
*wrong* and fails on a green tree — but that failure surfaces on a 101-line YAML-only PR where it
is trivially diagnosable, instead of inside a 400-line schema PR where it would look like a schema
bug. That is the argument for first, and it is a strong one.

---

### PR 2 — `docs/auth-and-scoping-design`

**Title:** the design record behind account scoping, pairing and the auth seam

**Base:** `ci/server-workflow`

**Contents (whole-file, 11 files, ~6680 lines):**
- `design/boomerang-account-scoping.md` *(new, 1327)*
- `design/boomerang-pairing-persistence.md` *(new, 1028)*
- `design/boomerang-extension-auth-proposal.md` *(new, 860)*
- `design/boomerang-auth-open-decisions.md` *(new, 550)*
- `design/boomerang-deployment-topology.md` *(new, 522)*
- `reviews/boomerang-high-level-design-review-2026-09-13.md` *(new, 518)*
- `reviews/boomerang-low-level-design-review-2026-09-13.md` *(new, 735)*
- `plan/boomerang-pr-stack.md` *(new, ~1380 — this document: the execution plan the six branches
  below follow. It is untracked like the other nine new files above and belongs to the same
  planning-prose branch; see §0.2's note on why it must ship rather than being left uncommitted.)*
- `design/boomerang-api-contract.md` *(modified, +356 — cross-origin/CSRF, the 401 discriminator,
  auth routes, caller enforcement, the abandonment reset)*
- `plan/boomerang-decisions.md` *(modified, +90 — the abandoned-run sub-decision, the
  revocation-scope decision, closed decisions section)*
- `infra/AGENTS.md` *(modified, +57 / −99 — rewritten to "Current state" / "What to do here")*

**What a reviewer is asked to judge.** The arguments, not the code. Whether account scoping should
be enforced by composite foreign keys rather than by discipline in query construction; whether the
pairing table's deliberate *lack* of account scoping is correct; whether the `401` discriminator
and the CSRF posture in the API contract are right; whether the revocation-scope decision is settled.
Every subsequent branch in this stack is an implementation of a decision recorded here, so this is
where a reviewer should push back on direction — arguing about a `ForeignKeyConstraint` in branch 3
when the real disagreement is with the account-scoping document wastes both people's time.

**Staging:** whole-file, all eleven.

**Green?** Yes, trivially. No file under `server/` is touched, so the CI workflow's path filter does
not even fire. There is nothing to run.

**Why not split the docs across the code branches they justify?** `AGENTS.md` says "when a doc and
the code disagree, fix it in the same PR", and the strict reading would put the account-scoping
document and the pairing-persistence document both in branch 3 — the branch that now folds the
composite-key rework, the duplicate-order fix and the auth-persistence tables together. Three reasons
not to. The documents cross-reference each other heavily and land half-dangling if pulled apart from
each other. `design/boomerang-api-contract.md`'s 356 lines arrive as eleven hunks spanning auth,
errors, routes and the abandonment reset — splitting them across the branches that implement each
part is hunk surgery on prose for no review benefit. And the `AGENTS.md` rule exists to stop docs
going *stale*; landing them one branch *early* does not make anything stale, it front-loads the
context. The docs describe work that is landing in the same stack, not work that shipped months ago.

---

### PR 3 — `feat/account-scoped-composite-keys`

**Title:** account-scoped composite keys, the duplicate-order fix, and the auth-persistence tables

**Base:** `docs/auth-and-scoping-design`

**Contents (whole-file, 5 files, ~+948):**
- `server/app/db/models.py` *(modified, 418 — the `nulls_not_distinct` fix, the composite-key
  rework, and the four auth tables, all three landing in one commit)*
- `server/app/db/mappers.py` *(modified, 15 — whole-file, the `account_id` parameter threading
  through the four mapper functions)*
- `server/tests/test_db_mappers.py` *(modified, 8 — whole-file, the four call-site updates)*
- `server/tests/test_db_models.py` *(modified, 167 — the composite-key constraint tests and the
  five auth tests)*
- `server/tests/test_db_integration.py` *(modified, 340 — the duplicate-order test, the
  `_expected_graph()` update, the cross-account composite-FK tests, and the auth-table tests)*

**What this branch folds together, and why it can.** This is branches 3, 4 and 5 of the original
nine-PR plan, merged by taking two of §6.4's three sanctioned collapses (fold PR 3 into PR 4, fold
PR 5 into PR 4). All five files above previously carried changes belonging to more than one of those
three PRs — see §3's entanglement table for the detail — which meant nine hand-authored intermediate
file states across `models.py`, `test_db_integration.py` and `test_db_models.py`, including the worst
hunk in the whole stack (`nulls_not_distinct` and the account-scoping rework interleaved line by line
inside one hunk of `models.py`). Folding all three original PRs into one branch means every one of
those five files now reaches its final working-tree state in a single commit. There is nothing left
to interleave, and no intermediate to author. **Confirmed against §3 and §0.2**: no other branch in
this six-branch stack touches any of these five files, so "whole-file" here is not an approximation.

**What a reviewer is asked to judge.** Three things, landing together, and the branch's honest cost is
that they no longer get three separate review passes.

First, the central security claim of the whole stack: after this change, a query that forgets its
account filter cannot reach another account's row, because the row's identity does not exist without
the account in it. `account_id` becomes a leading primary-key column on `order_items`,
`return_policies`, `policy_rules` and `return_summaries`; children point at `(account_id, parent_id)`
rather than `(parent_id)`; `MATCH FULL` so the guarantee survives `order_id` ever becoming nullable;
`NOT DEFERRABLE` so a mismatched child is rejected at the statement rather than at `COMMIT`; and never
`ON UPDATE CASCADE` on `account_id`, which would silently relabel a row into another account.
`orders.id` and `order_items.id` stay globally unique on purpose — a wire identifier must still name
at most one row — and `ix_orders_account_id` is dropped because `uq_orders_account_id_id`'s unique
index leads with `account_id` and serves the same prefix lookups.

Second, a duplicate-order fix that shares the same table: `retailer_order_reference` is nullable, and
PostgreSQL treats NULLs in a unique constraint as distinct, so a rescan of an order whose reference
could not be read currently inserts a second row for the same physical order.
`postgresql_nulls_not_distinct=True` on `uq_orders_retailer_reference` makes the second insert raise
`IntegrityError` instead. The tradeoff the reviewer must accept or reject: two genuinely different
unreadable-reference orders from the same retailer now collide too, and the second is rejected. There
is no available fact to tell those cases apart, so a loud, retryable failure is the honest outcome.
**This argument now has to be won inside a ~950-line combined diff rather than on its own** — folding
PR 3 into PR 4 (original numbering) was the first thing §6.4 said to give up, and this is the cost it
named.

Third, four tables for the pairing, grant, credential and revocation model: `AuthGrantRow` and
`AuthCredentialRow` follow the composite-key pattern above. `PairingRequestRow` and
`RevokedCredentialRow` deliberately do not — a pairing exists before any account is bound to it, so
there is nothing to put in a leading `NOT NULL` account column at creation, and a *nullable* column
inside a composite foreign key would silently skip the account check entirely under `MATCH SIMPLE`,
which is exactly the failure this table would otherwise reintroduce. `UNSCOPED_ROWS` is what turns
that exception into something a reviewer approves rather than a gap nobody notices: a row added later
that lands in neither the account-scoped registry nor this set fails an exhaustiveness check. **Say
this plainly: the unscoped `pairing_requests` exception now arrives in the same diff as the scoping
rule that makes it an exception.** Folding PR 5 into PR 4 (original numbering) was the third collapse
§6.4 sanctioned, and losing the isolated review of that exception is precisely the cost it warned
about. Also worth checking: `PairingStatus` has no `expired` member (expiry is evaluated against
`expires_at` at read time, never stored as a transition), and `BrowserLabel` is a closed
server-controlled vocabulary rather than a raw user-agent string, because the extension is the
untrusted party in the phishing scenario the label defends against.

**Staging:** whole-file, all five. Nothing in this branch requires a hand-authored intermediate.

**Green?** Yes. The new `test_db_models.py` tests are pure SQLAlchemy metadata inspection and the
auth tables' declarative class bodies execute at import — both run under `make cov`, not under the
integration marker. `mappers.py` gains only parameters, all exercised by the updated
`test_db_mappers.py`. No uncovered statement is introduced. The duplicate-order fix adds no
executable statement either (a keyword argument inside an existing constructor call). The
cross-account rejection tests, the auth-grant uniqueness test and the duplicate-order integration
test are all integration-marked and prove their respective constraints in CI's `integration` job, not
under `make cov` — say so in the PR body rather than letting a reviewer discover it.

**Can the rework separate from its tests?** No. Changing `order_item_to_row`'s signature breaks four
call sites in `test_db_mappers.py` in the same instant; changing `OrderItemRow`'s primary key breaks
`_expected_graph()` immediately. A "schema only" branch would be red and a "tests only" branch would
be red. They are one change, same as they were across the three original PRs this branch replaces.

**Why the auth tables land before the repository, not after.** `app/db/repository.py` (branch 4)
imports `UNSCOPED_ROWS` and builds an exhaustiveness check on it. Landing the auth tables here, at
their final value, means branch 4 simply consumes `UNSCOPED_ROWS` rather than needing a second edit
to it later.

---

### PR 4 — `feat/scoped-repository`

**Title:** confine unscoped queries to `app/db/` behind `ScopedRepository`

**Base:** `feat/account-scoped-composite-keys`

**Contents (whole-file, 3 files, ~+1185):**
- `server/app/db/repository.py` *(new, 344)*
- `server/tests/test_repository.py` *(new, 831)*
- `server/pyproject.toml` *(modified, +10 — whole-file, see below)*

**What a reviewer is asked to judge.** The enforcement layer that turns the previous branch's schema
guarantee into something the *application* also cannot get wrong. Three things. First
`ScopedRepository` itself: a session plus an account id, with every read filtered by
`ACCOUNT_COLUMN[Row] == account_id` and every write scoped the same way, including the
`reset_return_summary_if_abandoned` conditional update and its serialization-failure handling. Second
the `ACCOUNT_COLUMN` registry and `unscoped_rows()`: a row added later that lands in neither
`ACCOUNT_COLUMN` nor `UNSCOPED_ROWS` fails the exhaustiveness test, so forgetting to scope a new
table is a test failure rather than a silent hole. Third — and this is the part a reviewer might not
expect in this PR — the `TID251` banned-api rules in `pyproject.toml`, which make `sqlalchemy.select`
and `sqlalchemy.ext.asyncio.AsyncSession` lint errors anywhere outside `app/db/*`. That is what stops
the next route author from reaching past the repository.

**Staging:** whole-file, all three. `server/pyproject.toml`'s diff is not mixed. On inspection all
ten added lines are TID251 — the `"TID251"` entry in the `tests/*` per-file ignore list, the new
`"app/db/*"` per-file ignore, and the two `[tool.ruff.lint.flake8-tidy-imports.banned-api]` entries.
Nothing unrelated. It stages whole and it belongs here, with the code whose existence its error
messages assert.

**Green?** **Probably, and this is the boundary I am least sure of.** The reasoning: `make cov` runs
`pytest -m "not integration"`, and `test_repository.py`'s integration marker first appears at line
471 — lines 1–470 hold roughly twenty-five unit tests against fake sessions covering `get_account`,
`get_order`, `get_order_item`, `get_return_policy`, `get_return_summary`, `get_preference_set`,
`list_orders`, `list_order_items`, `replace_preference_set` (including the empty-values and
duplicate-values branches) and all five `reset_return_summary_if_abandoned` outcomes including the
serialization-failure and non-serialization-`DBAPIError` paths. That reads like deliberate,
branch-aware coverage of a 344-line module. But the file was still being written while this was
planned and I did not run the suite. **The executor must run the isolated worktree gate in §5.2 against
this commit before opening the PR, and must not proceed to branch 5 until it is green.** If coverage
falls short, the answer is more tests in `test_repository.py` in this PR — never a lower floor.

**Lint pre-check.** Introducing the `sqlalchemy.select` ban is safe: no module under `app/` outside
`app/db/` imports `select` today, so the ban lands without a single new finding.

---

### PR 5 — `feat/http-layer-and-me-route`

**Title:** one error shape, the auth seam, the `/v1` router, and the signed-in account's own profile

**Base:** `feat/scoped-repository`

**Contents (mixed, 10 files, ~+1470):**
- `server/app/api/errors.py` *(new, 269 — whole-file)*
- `server/app/api/auth.py` *(new, 107 — whole-file)*
- `server/tests/test_errors.py` *(new, 212 — whole-file)*
- `server/tests/test_auth.py` *(new, 148 — whole-file)*
- `server/app/api/deps.py` *(new, 147 — whole-file)*
- `server/app/routes/me.py` *(new, 49 — whole-file)*
- `server/app/routes/__init__.py` *(modified — **hand-authored intermediate**: the new docstring,
  `api_router = APIRouter(prefix="/v1")`, and the `me` import and include **only**. The `items`
  import and include are held back for branch 6.)*
- `server/app/main.py` *(modified, +26 — whole-file)*
- `server/tests/conftest.py` *(modified, +69 — whole-file)*
- `server/tests/test_routes_me.py` *(new, 420 — whole-file)*

**What this branch folds together, and why.** This is branches 7 and 8 of the original nine-PR plan,
merged by taking the second of §6.4's three sanctioned collapses (fold PR 7 into PR 8). Unlike the
fold that produced branch 3, this one saves no hand-editing at all — both halves were already
whole-file — so what it buys is a shorter stack and one fewer review round, and what it costs is
that the error envelope and the auth seam no longer get a review pass of their own, on paper, before
anything raises through them.

**What a reviewer is asked to judge.** Two contracts and the wiring and route that prove them, as one
change. The error envelope: `{reason, message, request_id}` on every failure, `request_id` on every
response and every log line, and the four handlers `install_error_handling` registers — `ApiError`,
`RequestValidationError` (including the `json_invalid` / `json_type` decode cases),
`StarletteHTTPException`, and the catch-all that must not leak an internal message at 500. The auth
seam: `AccountScope`, `_extract_authentication_inputs`, and `_resolve_account_id` — deliberately a
*seam*, not an implementation, so routes can be written and tested against a real dependency shape
while the credential resolution the design documents describe lands separately. `not_found_error`
making "absent" and "belongs to someone else" indistinguishable matters here and in branch 6 both.
The wiring: `/v1` lives once, on the aggregator in `app/routes/__init__.py`, so a route module
declares `@router.get("/me")` rather than `"/v1/me"` and `app.main` never needs touching again; the
database engine is built in the FastAPI `lifespan` alongside `bedrock.verify_config()`;
`DATABASE_URL` has no default in code and is validated at startup. The route: `GET /v1/me` takes no
account id from the caller, because the repository it receives is already bound to the principal's
account, and `AccountProfile` is an explicit response model rather than the ORM row — the only thing
keeping `google_subject` off the wire.

**The honest cost of merging these two.** A standalone version of the error envelope and auth seam
had one real objection against it: `errors.py` and `auth.py` were reachable only from tests, with no
production code path importing either until the router PR landed. Folding removes that objection —
`app.main` wires `install_error_handling` in the same commit that adds it — but it does so by giving
up the thing the split bought in exchange: a reviewer who wants to argue with the error contract on
its own terms, before it is entangled with routing and a route, cannot do that here. Both the wiring
and route diff and the contract diff arrive together, at roughly 1470 lines combined.

**Staging:** whole-file on nine, hand-authored intermediate on `routes/__init__.py`.

**Green?** Yes. `errors.py` and `auth.py`'s tests build their own throwaway `FastAPI` app and call
`install_error_handling` directly, so they do not depend on anything else in this branch. `deps.py`
has no dedicated test module — its coverage comes entirely from `test_routes_me.py`, which tests
`_require_database_url` directly and exercises `get_scoped_repository` and `_require_session_factory`
through the route. `test_routes_me.py` also covers `app/main.py`'s new wiring and the aggregator
prefix. `conftest.py`'s new fixtures (`stub_database_url`, `api_app`, `sign_in`, `serve_repository`)
import `app.routes.api_router` and `app.api.deps.get_scoped_repository`, both of which are introduced
in this same branch — so `conftest.py` stages whole here, same as before.

---

### PR 6 — `feat/v1-item-detail-route`

**Title:** serve one return candidate's full detail at `GET /v1/items/{item_id}`

**Base:** `feat/http-layer-and-me-route`

**Contents (mixed, 3 files, ~+930):**
- `server/app/routes/items.py` *(new, 294 — whole-file)*
- `server/app/routes/__init__.py` *(modified — **two lines**: `from app.routes import items` and
  `api_router.include_router(items.router)`. This completes the file to its working-tree state.)*
- `server/tests/test_routes_items.py` *(new, 635 — whole-file)*

**What a reviewer is asked to judge.** The product logic of the dashboard's detail view, which is the
first place in this stack where the server derives anything rather than storing it. Specifically:
`_derive_urgency`'s day thresholds and the `unknown` case when `return_by` is absent;
`_next_action`'s precedence table; `_money`, `_return_by` and `_fee`'s handling of the
`ReturnPolicyRow` partial-column cases; and the four not-found paths (absent item, missing order,
missing policy, missing summary). The one that matters most for security is
`test_cross_account_item_and_missing_item_are_byte_identical` — a foreign item and a nonexistent item
must produce the same bytes, or the endpoint becomes an existence oracle across accounts. Note the
route returns `return_by` as a date and never a countdown; a countdown computed server-side is frozen
the moment it is stored and silently wrong the next morning.

**Staging:** whole-file on two, two-line append on `routes/__init__.py`.

**Green?** Yes. `test_routes_items.py` is 635 lines against a 294-line module, using the
`serve_repository` fixture branch 5 introduced. The integration test at line 583
(`test_the_chain_hides_a_foreign_item_from_postgresql`) runs in CI's `integration` job.

**Dependency on in-flight work.** Both files in this PR were being written while this plan was made.
If `items.py` gains a second route, it belongs in this PR; the boundary does not move.

---

## 2. Where the PRs get big

| PR | Prod lines | Test lines | Reviewable in one sitting? |
|---|---:|---:|---|
| 1 | 101 | — | Yes |
| 2 | — | — | The docs are ~6680 lines (design/reviews prose plus this plan document); see below |
| 3 | ~433 | ~515 | Borderline — three original PRs' worth of schema and test changes in one commit |
| 4 | ~354 | 831 | Borderline — the largest single-mechanism PR |
| 5 | ~621 | ~849 | No — the largest PR in the stack, ~1470 lines combined |
| 6 | ~296 | 635 | Yes |

PR 2 is ~6680 lines of prose — the ten design/review documents plus this plan document itself — and no
reviewer will read it line by line. That is fine and expected — design documents are reference
material, reviewed by argument rather than by diff.

PR 3 and PR 5 are both larger than any single PR in the original nine-branch plan, and that is the
direct, named cost of the collapses taken at the top of this document. PR 3 folds a behavioural bug
fix, the account-scoping rework and four new tables into one ~950-line diff; PR 5 folds the error
envelope and auth seam into the same diff as the router and the `/me` route, at roughly 1470 lines
combined, and it is now the single largest PR in the stack. Neither resists splitting for a technical
reason — both would split cleanly back into their original PRs if the deadline eases — they are
simply the price of six branches instead of nine.

PR 4 is the one genuinely large PR that resists splitting on its own merits, independent of any
collapse: `ScopedRepository`, the `ACCOUNT_COLUMN` registry and the `TID251` ban are one mechanism,
and separating them would produce a PR whose lint rule references a class that does not exist yet.

---

## 3. The entanglement table

Folding the original PR 3, 4 and 5 into branch 3 (§6.4's first and third collapses) resolves three of
the five entanglements below outright: `models.py`, `test_db_integration.py` and `test_db_models.py`
each now reach their final working-tree state inside branch 3's single commit, because no other
branch in this six-branch stack touches them. **Verified against §0.2's inventory**: the "Belongs to"
column there names exactly one branch (branch 3) for each of the three files, where it used to name
three separate PRs. There is nothing left to interleave for them. One entanglement remains, and it is
the one §6.4 explicitly forbids collapsing away.

| File | Branches | Nature of the entanglement | How the split is achieved |
|---|---|---|---|
| `server/app/db/models.py` | **3 only** | Previously three unrelated reworks (original PR 3, 4, 5) in one 418-line diff, with the worst hunk interleaving the `nulls_not_distinct` fix and the `account_id` unique-constraint removal line by line. Folding those three PRs into branch 3 means the whole diff now lands in one commit. | **Whole-file.** No intermediate needed. |
| `server/tests/test_db_integration.py` | **3 only** | Same fold. The five test functions previously split across original PR 3, 4 and 5 all land together. | **Whole-file.** No intermediate needed. |
| `server/tests/test_db_models.py` | **3 only** | Same fold. The auth tests (original PR 5) and the composite-key constraint tests (original PR 4) land together. | **Whole-file.** No intermediate needed. |
| `server/app/routes/__init__.py` | **5, 6** | Unchanged by the fold. A 21-line file whose entire content is one replacement hunk; it imports and includes *both* `me` and `items`. Branch 5 must have only `me`, or `app.routes.items` does not exist and every import of `app.routes` fails. This is the boundary §6.4 rules out collapsing — old PR 8 and PR 9 stay apart as branches 5 and 6. | **Hand-authored intermediate in branch 5** (docstring + `api_router` + `me` only), then a **two-line completion** in branch 6. The only hand edit left in the entire stack. |
| `server/tests/conftest.py` | **5 only** | *Not actually entangled.* Every new fixture depends on `app.routes.api_router` or `app.api.deps.get_scoped_repository`, both introduced in branch 5. | **Whole-file in branch 5.** No split needed. |

**Explicitly *not* entangled**, contrary to the brief's original expectation:

- `server/pyproject.toml` — all ten added lines are TID251. Whole-file in branch 4.
- `server/app/db/mappers.py` — all five hunks are the `account_id` threading. Whole-file in branch 3.
- `server/app/main.py` — one coherent wiring change. Whole-file in branch 5.

**Bottom line.** After the fold, the only remaining hunk-level work in the entire six-branch stack is
`server/app/routes/__init__.py`, staged as a hand-authored intermediate in branch 5 and completed with
a two-line append in branch 6.

---

## 4. How to split a file without `git add -p`

`git add -i` and `git add -p` are unavailable, and `git add .` / `git add -A` are forbidden. Two
techniques are available. **Prefer the first.**

### 4.1 Hand-authored intermediates (recommended)

Only one file in this six-branch stack needs a hand-authored intermediate: `server/app/routes/__init__.py`,
at branch 5 (§3). The other three files this technique used to apply to — `models.py`,
`test_db_integration.py`, `test_db_models.py` — now reach their final state in one commit at branch 3
and need no intermediate at all. They are still copied aside below, and still restored-from-copy
rather than left as working-tree edits, purely as a defense against §6.1's risk: if an in-flight
agent touches one of them after the copy is taken, the working tree drifts but the pinned copy does
not.

For the one file that still needs an intermediate state, save the final working-tree version aside
once, write the file down to the intermediate state, stage it by explicit path, and restore the final
version at the end.

```bash
# once, before starting — the final content is the working tree as it stands today
mkdir -p /tmp/boomerang-final
cp server/app/db/models.py            /tmp/boomerang-final/models.py
cp server/tests/test_db_integration.py /tmp/boomerang-final/test_db_integration.py
cp server/tests/test_db_models.py      /tmp/boomerang-final/test_db_models.py
cp server/app/routes/__init__.py       /tmp/boomerang-final/routes__init__.py
```

Then at branch 5, edit `server/app/routes/__init__.py` down to the `me`-only state and `git add` that
explicit path. At branch 6, where the file reaches its final state, restore from
`/tmp/boomerang-final/` instead of editing, which guarantees the tree ends byte-identical to where it
started. `models.py`, `test_db_integration.py` and `test_db_models.py` are restored from their copies
at branch 3 the same way — not because they need editing, but because restoring from a pinned copy is
cheap insurance against the tree having moved since it was copied.

Why this and not patch surgery, for the one file that does need it: `routes/__init__.py`'s single
hunk either has `items` in it or it does not — hand-authoring the two states is simpler than
computing `@@` line counts for a two-line split, and it is verifiable by reading it.

**The cost, stated plainly.** One hand-authored file state, in one file, at one boundary. That is the
entire manual-editing burden of this six-branch stack — a direct result of the fold described at the
top of this document. The original nine-branch plan needed nine such states across four files.

**Safety property.** Because the final content is copied to `/tmp/boomerang-final/` before anything
starts, no intermediate edit can lose work. Verify at the end with the content-hash manifest described
in §7's closing steps, not with `git stash create` — that command does not capture untracked files, and
nineteen of the twenty new files this stack adds are untracked, so a snapshot built from it would be
missing nearly everything and would make every one of those files look like a spurious new addition
when compared against the finished stack. The manifest in §7 hashes every tracked *and* untracked,
non-ignored file up front and compares the same hash set at the end, which is what actually proves the
tip of the stack is byte-identical to the tree you began with.

### 4.2 Split patches via `git apply --cached` (fallback)

This technique was previously relevant to `test_db_integration.py` and `test_db_models.py`, whose
original PR-3/4/5 content arrived as **append-only** trailing hunks. Neither file needs splitting
anymore — both reach their final state whole, at branch 3 (§3, §4.1) — so this fallback currently has
no file to apply to. It is kept here in case the six-branch fold is ever partially reversed (for
example, un-collapsing branch 3 back toward the original PR 3/4/5 boundaries), since append-only
trailing hunks are the one shape in this stack where patch surgery is viable without hand-recomputing
interleaved `@@` line counts:

```bash
git diff server/tests/test_db_integration.py > /tmp/tdi.patch
# hand-edit /tmp/tdi.patch to keep only the wanted test bodies, fixing the @@ counts
git apply --cached /tmp/tdi.patch
```

Do **not** use this for `models.py`'s interleaved hunk even if it is ever re-split — the interleaving
there is line-by-line inside one hunk, not append-only.

### 4.3 A safety net for `git add .`

Since the prohibition on `git add .` / `git add -A` is the kind of thing a tired executor breaks at
2 a.m., it is worth setting the guard for the duration:

```bash
git config --local alias.add '!f() { case " $* " in *" . "*|*" -A "*|*" --all "*) echo "blocked: stage explicit paths"; return 1;; esac; command git add "$@"; }; f'
```

Remove it when the stack is done. (This is a suggestion, not part of the required script.)

---

## 5. Verifying each PR before it is opened

### 5.1 What actually runs where

This matters and is easy to get wrong:

| Gate | Command | Runs integration tests? |
|---|---|---|
| Coverage floor | `make cov` → `pytest -m "not integration" --cov` | **No** |
| Unit suite | `make test` → `pytest -m "not integration"` | **No** |
| Integration | `make integration` → `pytest -m integration` | Yes, needs `TEST_DATABASE_URL` |
| CI `quality` job | fmt-check, lint, typecheck, cov, audit (advisory) | **No** |
| CI `integration` job | `make integration` against a `postgres:17.11` service | Yes |

So `fail_under = 95` is computed over the Docker-free run only. Any module whose only tests are
integration-marked contributes uncovered lines to the floor. That is exactly why `deps.py` has to be
staged together with its own tests rather than separated across branches — in this six-branch shape
that means it lands in branch 5 alongside `test_routes_me.py`, not any earlier — and it is the check
to repeat by hand if any boundary in this stack is moved.

### 5.2 Per-branch gate: verify the commit in isolation, not the working tree

An earlier version of this plan ran `make -C server check` against the working tree, before each
branch's `git add`. That gate was decorative. From the first `git checkout -b` to the last, the
working tree holds the **complete final state of all six branches at once** — committing a subset of
files does not remove the rest from disk. By branch 3, the working tree already contains
`server/app/db/repository.py`, all of `server/app/api/`, both route modules and every test file, none
of which branch 3 has staged. The check passed because everything was physically present, and it
would have passed just as happily if branch 3's own five files were badly broken in isolation. It
could not do the one thing a stacked-PR gate exists to do: prove that the commit a reviewer is about
to see is green **on its own**, because CI runs each PR against exactly that commit and nothing else.

The fix is to check out the commit that was just made, in a location that holds nothing else, and run
the gate there:

```bash
git worktree add --detach /tmp/boomerang-verify <branch-name>
make -C /tmp/boomerang-verify/server install
make -C /tmp/boomerang-verify/server check
git worktree remove --force /tmp/boomerang-verify
```

Two details in this that are not incidental:

**`--detach` is required, not a style choice.** At the point this runs, `<branch-name>` is still
checked out in the main working copy — that is what `git checkout -b` did to get here. `git worktree
add` refuses to check out a branch that is already checked out somewhere else. `--detach` checks out
the branch's *commit* rather than the branch itself, which proves the same thing (that commit's tree,
in isolation) without trying to attach a second working copy to the same branch ref.

**`install` before `check` is required, not optional.** Read against `server/Makefile`: `check` is
`fmt-check lint typecheck cov audit`, and none of those targets syncs the environment — every one of
them shells out to `uv run`, and `uv run` improvises an environment on first use if none exists, but
doing that once via `install` (`uv sync --all-groups`) rather than five separate times is what the
named target is for. It matters more here than it does day to day, because `git worktree add` produces
a genuinely fresh checkout: `server/.gitignore` excludes `.venv`, so a new worktree has no virtual
environment at all, unlike a developer's long-lived clone where one already exists.

**This is slower than the working-tree version it replaces, and that is the honest cost of it actually
verifying something.** A fresh `make install` builds a full virtual environment from `uv.lock` from
nothing, and this runs once per branch from branch 3 onward, not once for the whole stack. `make
audit` also reaches out to the CVE database on every one of those runs. Budget for it — the four
`make check` invocations this replaces were fast for a reason, and the reason was that they were not
checking anything.

**The gate necessarily runs after the commit, not before it** — there is no commit to check out until
it exists. Concretely, per branch from branch 3 onward, the shape is: commit, then verify, then push
only if verification passed. See §7 for the exact commands at each branch.

**If the gate is red, do not push.** The branch that failed is the only one in question. Every branch
below it in the stack was already verified this same way and is already pushed; no branch above it
exists yet, because this script builds and verifies one branch at a time before starting the next.
Recover one of two ways: amend the commit (fix the file or add the missing test, `git add` the same
explicit paths again, `git commit --amend`) and re-run the four-line gate above until it is green; or,
if the branch needs a different starting point, delete it and re-run its block from `git checkout -b`.
Either way, do not create the next branch in the stack until this one is green, and never lower
`fail_under` or add `# pragma: no cover` to get there — a failing floor means a missing test, full
stop.

**Does any branch in this six-branch layout fail this gate for a structural reason — a source file
landing before its own tests?** That is a real failure mode in principle: a branch containing a module
whose only tests arrive in a later branch will measure under 95% no matter how correct the code is,
because the tests that would prove it are not there yet to run. Checked against §1 and §0.2, file by
file: branch 3 ships `models.py` and `mappers.py` alongside `test_db_models.py`, `test_db_mappers.py`
and `test_db_integration.py`; branch 4 ships `repository.py` alongside `test_repository.py`; branch 5
ships `errors.py`, `auth.py`, `deps.py`, `routes/me.py`, `main.py` and `conftest.py` alongside
`test_errors.py`, `test_auth.py` and `test_routes_me.py` (`deps.py` has no dedicated test module, but
its coverage comes from `test_routes_me.py` in this same branch, not a later one — §5.1 already says
so); branch 6 ships `items.py` alongside `test_routes_items.py`. In every branch that touches
`server/`, the tests for what that branch adds are committed in the same branch as the code. No branch
in this layout is structurally forced under the coverage floor — that is a property of how §3 and
§4.1 drew the boundaries, not an accident, and it is the check to redo by hand if any boundary here is
ever moved. Branch 4 remains the one branch whose greenness this document could not observe directly
when it was written (§6.2); the difference this gate makes is that "run `make check` here" now checks
the tree that will actually become the PR, instead of a tree that already contains branches 5 and 6.

Branches 1 and 2 skip this gate, for the reason §5.1 already gives: branch 1 touches no Python and
branch 2 touches nothing under `server/`, so there is no `server/` commit to check out and nothing the
gate would exercise that differs from what already passed on `origin/main`.

---

## 6. Risks, and what I think is a bad idea

### 6.1 The in-flight agents (highest risk)

Three agents were writing `server/app/routes/items.py`, `server/app/routes/__init__.py` and
`server/app/db/repository.py` when this plan was written. §4.1's technique copies the "final" content
to `/tmp` at the start; if an agent writes to one of those files *after* that copy, the copy is stale
and the stack's tip will not match the tree. **Execution must not begin until all three agents have
finished.** Re-run §0.1 and §0.2 first and diff them against this document.

### 6.2 Branch 4's coverage is asserted, not measured

I did not run the suite — the tree is mid-edit and currently red for reasons that are not mine to
diagnose, and running it would have produced a failure I could not attribute. So every "green?"
verdict above is reasoned from the coverage configuration, the marker placement and the test
inventory, not observed. Branch 4 (originally PR 6) is where that reasoning is thinnest: 344
production lines against a test file that was still being written. If `make cov` comes in under 95 at
branch 4, the remedy inside this plan is more tests in `test_repository.py` in that same branch.

§5.2's isolated worktree gate is what turns "asserted" into "measured": it runs a fresh `make install`
and `make check` against branch 4's commit alone, in a location holding nothing from branches 5 or 6,
so a real shortfall now surfaces as a failing gate rather than as a paragraph written from reasoning
about test placement. I checked, while writing that gate, whether any branch in this six-branch layout
is *structurally* forced under the floor — a source file whose only tests arrive in a later branch —
and found none; see §5.2 for the file-by-file accounting. Branch 4 stays the one branch whose result
was genuinely unknown when this was written, not because of a forced boundary but because the file was
still being written.

That gate is not free. A fresh worktree has no `.venv` (`server/.gitignore` excludes it), so `make
install` builds one from scratch before `make check` can run, once per branch from branch 3 onward,
and `make audit` reaches out to the CVE database each time too. That is real time added to the
execution, in exchange for the "Green?" verdicts throughout this document meaning what they claim
rather than describing a tree that already contained the answer.

### 6.3 CI itself could be wrong

Branch 1 pins `actions/checkout@v7` and `astral-sh/setup-uv@v10.1.0`. I could not verify either tag
exists or that `make install` works on a clean runner with the committed `uv.lock`. If branch 1
fails, that is a *good* outcome — it fails on a 101-line YAML-only PR where the cause is obvious —
but expect a fix-up commit on that branch before the rest of the stack rebases onto it.

### 6.4 Splits collapsed to reach the six-branch shape, and the one collapse that is off the table

This enumerates the original nine-PR plan's collapse options, in the order they cost the least to the
most. **The six-branch shape adopted in this document takes all three** — see the note at the top of
this document and §6.5. They are kept here, against the original numbering, because the cost/benefit
reasoning for each still matters when reviewing the merged branches it produced (branch 3 and branch
5, in §1).

1. **Fold PR 3 into PR 4** (both now inside **branch 3**). Saved one `models.py` intermediate and one
   `test_db_integration.py` intermediate — the two most expensive hand edits in the original plan,
   since the interleaved hunk was in `models.py`. Cost: the duplicate-order tradeoff is reviewed
   inside a schema-and-auth-tables branch rather than on its own. This was the first thing to give
   up, and it went first.
2. **Fold PR 7 into PR 8** (both now inside **branch 5**). Produced one ~1470-line "HTTP layer"
   branch. Saved no hand-editing at all — both halves were already whole-file — so this bought only a
   shorter stack and fewer review rounds, at the cost of the error envelope getting no dedicated
   attention. Cheap to do, real loss.
3. **Fold PR 5 into PR 4** (both now inside **branch 3**, alongside the PR 3 fold above). Saved the
   remaining `models.py` and `test_db_models.py` intermediates and left **zero** hunk-level work in
   the entire stack except `routes/__init__.py`'s two lines. The result is branch 3: a ~950-line
   schema-and-auth-tables branch. Genuinely tempting on cost grounds, and genuinely worse on review
   grounds: the reviewer's job on the auth tables is to decide whether `PairingRequestRow`'s unscoped
   exception is correct, and that question is harder to see clearly when it arrives alongside the
   rule that established it.

**Not collapsed, and not to be collapsed.** Do **not** fold old PR 8 into old PR 9 — they stay apart
as branch 5 and branch 6 — and do not fold old PR 6 into anything — it stays alone as branch 4. Both
boundaries are dependency-forced and reviewability-forced, and both were free to keep. If anything
executed from this document merges those, that is a mistake, not a further optimization.

### 6.5 Is this split worth doing at all?

Yes, but the honest version has a shape.

Under the original nine-PR numbering, PRs 1, 2, 6, 7, 8 and 9 cost **nothing beyond branch
mechanics** — every file in them stages whole, and the only manual work anywhere in that set was two
lines of `routes/__init__.py`. That was six reviewable PRs for essentially the price of typing the
commands. There was no argument for shipping those six as one PR. One PR containing a CI workflow,
~6680 lines of design prose, a schema rework, a repository layer, an error envelope and two routes is
not a thing a person reviews; it is a thing a person approves.

PRs 3, 4 and 5 (original numbering) were where the money went: nine hand-authored file states across
three files, in a `models.py` whose worst hunk interleaved two PRs line by line. That was a couple of
focused hours and a real chance of a mistake that shows up as a red CI run two PRs later. It was still
worth it — account scoping is the security property the whole product rests on, and it deserves to be
judged without four new auth tables in the same diff — but it was the part to cut first if the
schedule forced a choice, in the order given in §6.4.

**The shape actually adopted in this document is six branches**, by taking all three collapses in
§6.4 — fold PR 3 into PR 4, fold PR 7 into PR 8, and fold PR 5 into PR 4, in the original numbering —
and stopping there, short of the two collapses §6.4 rules out. (An earlier version of this sentence
said "six PRs... by taking option 1 from §6.4 and leaving everything else" — folding one PR into
another out of nine leaves eight, not six. That was an arithmetic error; reaching six actually
requires all three collapses, which is what this document now does throughout.) Taking all three
removes every hand-authored intermediate for `models.py`, `test_db_integration.py` and
`test_db_models.py`, and it removes the error envelope's dedicated review pass along with it. Both
costs named in §6.4 are real and are being paid here: the duplicate-order tradeoff and the
`pairing_requests` unscoped exception are argued inside larger diffs rather than alone, and the error
contract gets no attention separate from the router and the `/me` route. Accept those costs as the
price of six branches under deadline — not as evidence the six-branch shape is free.

### 6.6 Smaller risks

- **The stack rebases.** Six stacked PRs means every merge of PR *n* requires PRs *n+1*…*6* to
  rebase. With squash-merge (which this repo uses — see `#9`, `#10`, `#11`) that is mechanical but
  not free. Merging strictly bottom-up and promptly keeps it manageable; letting branch 3 sit for a
  week while branch 6 is reviewed does not.
- **Branch 3 carries two independent arguments about the same table.** The duplicate-order fix's
  `nulls_not_distinct` argument and the composite-key rework's changes to `OrderRow.__table_args__`
  now land in the same commit. If a reviewer rejects the `nulls_not_distinct` argument, the fix is a
  same-branch re-author rather than a rebase of a downstream branch — but the two arguments share one
  accept-or-revert decision as a result, where the original nine-PR plan let them be judged apart.
- **`ix_orders_account_id` is dropped in branch 3** on the argument that `uq_orders_account_id_id`'s
  unique index serves the same prefix lookups. That reasoning is sound for PostgreSQL but is a
  performance claim with no benchmark behind it. Worth a reviewer's explicit nod rather than a silent
  pass.
- **`nulls_not_distinct` requires PostgreSQL 15+** and is silently ignored on any other backend. The
  comment says so. The integration job runs `postgres:17.11`, so CI proves it; a developer on an
  older local PostgreSQL would see the test fail confusingly.
- **`reviews/` is a new top-level directory** created in branch 2. Confirm that is intended and that
  `AGENTS.md`'s repo map should gain a row for it — the map currently lists `extension/`, `client/`,
  `server/`, `infra/`, `docs/`, `design/` and `.claude/`, and a new top-level directory that the map
  does not mention is exactly the kind of drift the map exists to prevent.

---

## 7. The execution script

**Do not run any of this without first completing §0.3 and §6.1.** Every `git add` names explicit
paths; `git add .` and `git add -A` appear nowhere.

```bash
set -euo pipefail
cd /Users/shinobi07/Desktop/projects/boomerang

# ---------------------------------------------------------------------------
# 0. Preserve the final content of every file this stack touches more than
#    once, and of the one file that still needs a hand-authored intermediate
#    state.
# ---------------------------------------------------------------------------
mkdir -p /tmp/boomerang-final
cp server/app/db/models.py             /tmp/boomerang-final/models.py
cp server/tests/test_db_integration.py /tmp/boomerang-final/test_db_integration.py
cp server/tests/test_db_models.py      /tmp/boomerang-final/test_db_models.py
cp server/app/routes/__init__.py       /tmp/boomerang-final/routes__init__.py

# A full content-hash manifest of the starting tree — tracked AND untracked,
# non-ignored files alike. `git stash create` was tried here first and
# rejected: it does not capture untracked files at all, and nineteen of the
# twenty new files this stack adds are untracked, so a stash-based snapshot
# would be missing nearly everything it needs to prove. This manifest is what
# the closing check in this script actually compares against.
git ls-files --cached --others --exclude-standard -z \
  | xargs -0 sha256sum | sort -k2 > /tmp/boomerang-final/MANIFEST.before

# ---------------------------------------------------------------------------
# PR 1 — ci/server-workflow
# ---------------------------------------------------------------------------
git checkout -b ci/server-workflow origin/main
git add .github/workflows/server.yml
git commit -F /tmp/boomerang-msg/01.txt
# No server/ Python here — nothing for the §5.2 isolation gate to check that
# CI (triggered by this push) does not already prove on its own.
git push -u origin ci/server-workflow

# ---------------------------------------------------------------------------
# PR 2 — docs/auth-and-scoping-design
# ---------------------------------------------------------------------------
git checkout -b docs/auth-and-scoping-design ci/server-workflow
git add design/boomerang-account-scoping.md \
        design/boomerang-auth-open-decisions.md \
        design/boomerang-deployment-topology.md \
        design/boomerang-extension-auth-proposal.md \
        design/boomerang-pairing-persistence.md \
        design/boomerang-api-contract.md \
        reviews/boomerang-high-level-design-review-2026-09-13.md \
        reviews/boomerang-low-level-design-review-2026-09-13.md \
        plan/boomerang-decisions.md \
        plan/boomerang-pr-stack.md \
        infra/AGENTS.md
git commit -F /tmp/boomerang-msg/02.txt
# No server/ Python here either.
git push -u origin docs/auth-and-scoping-design

# ---------------------------------------------------------------------------
# PR 3 — feat/account-scoped-composite-keys
#
# No manual editing. This branch folds the original PR 3/4/5 boundary away —
# all five files below reach their final working-tree state here, in one
# commit. Restore the three that have a preserved copy (defends against
# §6.1's in-flight-agent risk); the other two are staged as they already
# stand.
# ---------------------------------------------------------------------------
git checkout -b feat/account-scoped-composite-keys docs/auth-and-scoping-design
cp /tmp/boomerang-final/models.py              server/app/db/models.py
cp /tmp/boomerang-final/test_db_models.py      server/tests/test_db_models.py
cp /tmp/boomerang-final/test_db_integration.py server/tests/test_db_integration.py
git add server/app/db/models.py \
        server/app/db/mappers.py \
        server/tests/test_db_models.py \
        server/tests/test_db_mappers.py \
        server/tests/test_db_integration.py
git commit -F /tmp/boomerang-msg/03.txt

# --- verify this commit in isolation (§5.2) — after the commit, not before ---
git worktree add --detach /tmp/boomerang-verify feat/account-scoped-composite-keys
make -C /tmp/boomerang-verify/server install
make -C /tmp/boomerang-verify/server check
git worktree remove --force /tmp/boomerang-verify
# If either `make` above failed: STOP, do not push. Amend this commit (fix the
# file, re-`git add` the same explicit paths, `git commit --amend`) and re-run
# the four lines above until green, or delete this branch and re-cut it from
# `git checkout -b` above. Branches 1 and 2 are already pushed and unaffected
# either way — nothing has been built on top of this one yet.

git push -u origin feat/account-scoped-composite-keys

# ---------------------------------------------------------------------------
# PR 4 — feat/scoped-repository
# ---------------------------------------------------------------------------
git checkout -b feat/scoped-repository feat/account-scoped-composite-keys
git add server/app/db/repository.py \
        server/tests/test_repository.py \
        server/pyproject.toml
git commit -F /tmp/boomerang-msg/04.txt

# --- verify this commit in isolation (§5.2) ---------------------------------
# This is the boundary §6.2 flags as asserted, not measured, when this plan
# was written. This is where that actually gets settled.
git worktree add --detach /tmp/boomerang-verify feat/scoped-repository
make -C /tmp/boomerang-verify/server install
make -C /tmp/boomerang-verify/server check
git worktree remove --force /tmp/boomerang-verify
# If coverage falls short here, the fix is more tests in test_repository.py in
# THIS branch (amend the commit) — never a lower fail_under, never a pragma.
# Do not proceed to branch 5 until this is green. Same recovery as branch 3
# above otherwise.

git push -u origin feat/scoped-repository

# ---------------------------------------------------------------------------
# PR 5 — feat/http-layer-and-me-route
#
# MANUAL STEP. server/app/routes/__init__.py must contain the docstring, the
# `api_router = APIRouter(prefix="/v1")` line, and the `me` import/include
# ONLY. Hold back the two `items` lines for PR 6. This is the only
# hand-authored intermediate left in the entire stack.
# ---------------------------------------------------------------------------
git checkout -b feat/http-layer-and-me-route feat/scoped-repository
# <manual edit of server/app/routes/__init__.py here>
git add server/app/api/errors.py \
        server/app/api/auth.py \
        server/tests/test_errors.py \
        server/tests/test_auth.py \
        server/app/api/deps.py \
        server/app/routes/me.py \
        server/app/routes/__init__.py \
        server/app/main.py \
        server/tests/conftest.py \
        server/tests/test_routes_me.py
git commit -F /tmp/boomerang-msg/05.txt

# --- verify this commit in isolation (§5.2) ---------------------------------
git worktree add --detach /tmp/boomerang-verify feat/http-layer-and-me-route
make -C /tmp/boomerang-verify/server install
make -C /tmp/boomerang-verify/server check
git worktree remove --force /tmp/boomerang-verify
# Same recovery as branch 3 above if red: amend or re-cut, do not proceed
# until green.

git push -u origin feat/http-layer-and-me-route

# ---------------------------------------------------------------------------
# PR 6 — feat/v1-item-detail-route
#
# server/app/routes/__init__.py reaches its FINAL state here, so restore
# rather than edit.
# ---------------------------------------------------------------------------
git checkout -b feat/v1-item-detail-route feat/http-layer-and-me-route
cp /tmp/boomerang-final/routes__init__.py server/app/routes/__init__.py
git add server/app/routes/items.py \
        server/app/routes/__init__.py \
        server/tests/test_routes_items.py
git commit -F /tmp/boomerang-msg/06.txt

# --- verify this commit in isolation (§5.2) ---------------------------------
git worktree add --detach /tmp/boomerang-verify feat/v1-item-detail-route
make -C /tmp/boomerang-verify/server install
make -C /tmp/boomerang-verify/server check
git worktree remove --force /tmp/boomerang-verify
# Same recovery as branch 3 above if red.

git push -u origin feat/v1-item-detail-route

# ---------------------------------------------------------------------------
# Verify the tip of the stack is byte-identical to the tree we started from.
# Both checks below are expected to produce no output.
# ---------------------------------------------------------------------------
git status --porcelain   # every file in §0.2's inventory, plan/boomerang-pr-stack.md
                         # included, now belongs to some branch in the stack

git ls-files --cached --others --exclude-standard -z \
  | xargs -0 sha256sum | sort -k2 > /tmp/boomerang-final/MANIFEST.after
diff /tmp/boomerang-final/MANIFEST.before /tmp/boomerang-final/MANIFEST.after
```

Open the PRs bottom-up, each targeting the branch below it:

```bash
gh pr create --base main                              --head ci/server-workflow                --title "..." --body-file /tmp/boomerang-pr/01.md
gh pr create --base ci/server-workflow                 --head docs/auth-and-scoping-design      --title "..." --body-file /tmp/boomerang-pr/02.md
gh pr create --base docs/auth-and-scoping-design       --head feat/account-scoped-composite-keys --title "..." --body-file /tmp/boomerang-pr/03.md
gh pr create --base feat/account-scoped-composite-keys --head feat/scoped-repository             --title "..." --body-file /tmp/boomerang-pr/04.md
gh pr create --base feat/scoped-repository             --head feat/http-layer-and-me-route       --title "..." --body-file /tmp/boomerang-pr/05.md
gh pr create --base feat/http-layer-and-me-route       --head feat/v1-item-detail-route          --title "..." --body-file /tmp/boomerang-pr/06.md
```

---

## 8. Commit and PR message drafts

House style, taken from `git log -3 --format=full` (`fa6339f`, `100f795`) and `git log --oneline -20`:
lowercase prose subject line, no trailing period, no conventional-commit prefix on the squash-merged
PR title; body wrapped near 80 columns; the body explains *why* it changed; a `dev-note` or a TODO
stated plainly where one exists. Earlier commits inside `#9` used `feat(server):` prefixes — the two
most recent merges did not, and these follow the recent style.

**No requirement IDs, section numbers or ticket ids are cited in any message below.** The document
you are reading uses them elsewhere for cross-reference; a commit message is read by someone who has
not read this document, so it explains itself instead of pointing at a section number.

**No Claude or Anthropic attribution appears in any message below.** No `Co-Authored-By`, no
"Generated with", no session trailer, no marker of any kind. Existing commits on `main` carry a
`Claude-Session:` trailer; that practice stops here. Each message ends with its own last line of
prose.

---

### 01 — `ci/server-workflow`

**Commit / PR title:** `run the server's quality gate on every pull request`

```
run the server's quality gate on every pull request

server/AGENTS.md has said "run make -C server check and paste the result" since
the tooling landed, and nothing has enforced it. The pre-commit hook can be
bypassed with --no-verify and is not installed at all on a fresh clone until
someone runs make setup-hooks.

Two jobs, mirroring what already exists rather than inventing a second standard:

- quality runs make install, fmt-check, lint, typecheck and cov, in that order.
  make audit runs last with continue-on-error, matching scripts/pre-commit-server.sh
  — a fresh CVE in a transitive dependency is not the committer's fault and
  blocking every build on it is how gates get disabled wholesale. Its output still
  belongs in the log.
- integration runs make integration against a postgres service pinned to the same
  image, credentials and database name as server/compose.integration.yml. make cov
  runs `pytest -m "not integration"`, so without this job nothing exercises the
  CHECK constraints, the composite foreign keys or the round trip.

Path filters keep client, docs, design, plan and infra changes off the runner. The
filter includes this file, so a change to the workflow tests itself.

concurrency cancels a superseded run on the same ref rather than letting both
finish.
```

**PR body:** the commit message, plus:

```
First in a stack of six. Landing CI before the work it checks means every later
branch in the stack is gated by the real runner against the real PostgreSQL
service, rather than by five separate claims that make check passed locally. It
runs against main's tree here, which is green.

Stack: this → docs → account-scoped composite keys (with the duplicate-order
fix and the auth-persistence tables folded in) → scoped repository → the HTTP
layer (error envelope, auth seam, /v1 router, /me) → /v1/items.
```

---

### 02 — `docs/auth-and-scoping-design`

**Commit / PR title:** `the design record behind account scoping, pairing and the auth seam`

```
the design record behind account scoping, pairing and the auth seam

The code in the rest of this stack implements decisions argued here. Landing the
arguments first means a reviewer who disagrees with the direction can say so
before reading a ForeignKeyConstraint.

New:

- design/boomerang-account-scoping.md — why account scoping is enforced by
  composite foreign keys rather than by discipline at the query site, and what
  MATCH FULL and NOT DEFERRABLE each buy.
- design/boomerang-pairing-persistence.md — the pairing lifecycle, and the
  argument for pairing_requests being deliberately unscoped.
- design/boomerang-extension-auth-proposal.md — how a browser is linked to an
  account without a Google scope.
- design/boomerang-auth-open-decisions.md — what is still open, stated as
  questions rather than as guesses.
- design/boomerang-deployment-topology.md — the topology the infra scaffold no
  longer describes.
- reviews/ — the high-level and low-level design reviews from 2026-09-13, kept
  because the objections they raise are load-bearing for the decisions above.
- plan/boomerang-pr-stack.md — the plan that splits this working tree into the
  six branches this stack is made of. It travels with the rest of the planning
  record rather than staying uncommitted paperwork nobody can point a reviewer
  at.

Changed:

- design/boomerang-api-contract.md gains a cross-origin and request-forgery
  section, the 401 discriminator, the authentication routes, caller
  enforcement, and the abandonment reset.
- plan/boomerang-decisions.md records the sub-decision on the abandoned run and
  the stranded summary, the decision on revocation scope, and separates closed
  architecture decisions from open ones.
- infra/AGENTS.md is rewritten. It described the Lambda scaffold as though it were
  the plan; it is not, and a reader arriving there was being misled about the
  production topology. It now states what is actually there and what to do with it.

No file under server/ changes, so the server workflow does not run.
```

---

### 03 — `feat/account-scoped-composite-keys`

**Commit / PR title:** `account-scoped composite keys, the duplicate-order fix, and the auth-persistence tables`

```
account-scoped composite keys, the duplicate-order fix, and the auth-persistence tables

Until now, one account's data was kept out of another's by every query
remembering to filter on account_id, and a rescanned order whose reference
could not be read silently duplicated instead of being rejected. Both are the
same kind of problem: a guarantee that lived in someone's discipline rather
than in the schema. This closes both, and adds the tables the next layer
needs, together, because they touch the same tables and the same tests.

account_id becomes a leading primary-key column on order_items, return_policies,
policy_rules and return_summaries, and each child's foreign key points at
(account_id, parent_id) rather than at (parent_id). A row whose account does not
match its parent's cannot be written, so the account check no longer depends on
a query getting it right — the row shape carries it. MATCH FULL, so the
guarantee does not quietly depend on order_id staying NOT NULL forever. NOT
DEFERRABLE, so a mismatched child is rejected at the statement rather than at
COMMIT. Never ON UPDATE CASCADE on account_id, which would silently relabel a
row into another account. orders.id and order_items.id stay globally unique,
because a wire identifier must still name at most one row.

Alongside that, uq_orders_retailer_reference gets postgresql_nulls_not_distinct.
retailer_order_reference is nullable, and PostgreSQL treats NULLs in a unique
constraint as distinct by default, so a rescan of an order whose reference
could not be read was inserting a second row for the same order — the same
physical order, twice, each copy with its own item ids, policies and
not-started summary. This makes the second insert collide and raise
IntegrityError instead. The tradeoff: two genuinely different
unreadable-reference orders from the same retailer now collide too, and the
second is rejected. There is no available fact to tell those cases apart, so a
loud, retryable failure is the honest outcome rather than a guess.

Four tables land on the same schema. auth_grants and auth_credentials follow
the composite-key pattern above. pairing_requests and revoked_credentials
deliberately do not — a pairing exists before any account is bound to it, so
there is nothing to put in a leading NOT NULL account column at creation, and a
nullable column inside a composite foreign key would skip the account check
entirely under MATCH SIMPLE, which is precisely the failure this change exists
to close. So pairing_requests carries a plain nullable account foreign key, no
account-derived data, and an entry in UNSCOPED_ROWS instead. Worth being direct
about: that exception arrives in the same diff as the rule that makes it an
exception, rather than being reviewed on its own. UNSCOPED_ROWS is what keeps
it from becoming a habit regardless — a row added later that lands in neither
the account-scoped registry nor this set fails an exhaustiveness check.

Two vocabulary decisions in the new tables are worth checking: PairingStatus
has no expired member, because expiry is evaluated against expires_at at read
time, never stored as a transition of its own. And BrowserLabel is a closed,
server-controlled set rather than a raw user-agent string, because the
extension is the untrusted party in the phishing scenario the label defends
against.

Schema and tests land together throughout — changing order_item_to_row's
signature breaks four call sites in test_db_mappers.py in the same instant, and
changing OrderItemRow's primary key breaks the expected-graph assertions
immediately. None of this separates into a schema-only or tests-only change.

The nulls_not_distinct behavior and the composite foreign key rejections are
both proven by integration tests, so make cov does not exercise them — make
integration and the CI integration job do.

See design/boomerang-account-scoping.md and design/boomerang-pairing-persistence.md.
```

---

### 04 — `feat/scoped-repository`

**Commit / PR title:** `confine unscoped queries to app/db/ behind ScopedRepository`

```
confine unscoped queries to app/db/ behind ScopedRepository

The schema now makes a cross-account row unwritable. This makes a cross-account
row unreadable, and does it in a way that does not rely on the next person
remembering.

ScopedRepository is a session plus an account id. Every read filters on
ACCOUNT_COLUMN[row] == account_id and every write is scoped the same way, so a
caller never passes an account id and therefore never passes the wrong one. There
is no unscoped accessor to reach for.

ACCOUNT_COLUMN is a registry, and unscoped_rows() subtracts it and
models.UNSCOPED_ROWS from ORM_ROWS. A table added later that is in neither set
comes back from that call and fails a test. Forgetting to scope a new table is a
red build rather than a quiet hole.

reset_return_summary_if_abandoned is the one non-trivial write. It is a
conditional update returning the row it changed, so a lost race is observable
rather than inferred, and a PostgreSQL serialization failure is reported as a lost
race rather than raised — two callers racing to reset the same abandoned summary
is an expected outcome, not an error. Any other DBAPIError still propagates.

pyproject.toml is where the rule gets teeth. TID251 bans sqlalchemy.select and
sqlalchemy.ext.asyncio.AsyncSession everywhere except app/db/*, so the next route
author who reaches past the repository gets a lint failure with a message naming
what to use instead. tests/ is exempt: tests build fixtures and verify boundary
failures directly against the schema — cross-account setup, composite-FK
rejection — and the boundary this rule protects is app/db/ against everything
above it, not against the suite that proves it works.

No app module outside app/db/ imports select today, so the ban lands clean.
```

---

### 05 — `feat/http-layer-and-me-route`

**Commit / PR title:** `one error shape, the auth seam, and the /v1 router that serves the account's own profile`

```
one error shape, the auth seam, and the /v1 router that serves the account's own profile

The HTTP layer, in one change: the error contract every route depends on, the
seam that resolves a caller to an account, the router that mounts them, and the
first route that proves all three together.

{reason, message, request_id} on every failure, and request_id on every
response and every log line — success included. That last part is not
decoration: order contents, item titles, addresses and confirmation numbers are
unloggable at any level, DEBUG included, so with the redacting formatter in
place request_id is the only correlator that survives a user's bug report back
to a log line. It is deliberately opaque — not a session id, and nothing should
correlate two requests from one install.

install_error_handling registers four handlers. ApiError carries its own
reason. RequestValidationError becomes a field-level message, with the decode
failures for bad JSON and for a wrong field type separated out, because they
are different problems for the caller. StarletteHTTPException is normalised
into the same envelope, so a 404 from the framework and a 404 from a handler
are indistinguishable on the wire. The catch-all logs the exception and returns
a fixed message — a 500 must never leak an internal string. not_found_error is
deliberately the same response for "does not exist" and "belongs to someone
else"; a distinguishable 403 turns every id-taking endpoint into an existence
oracle across accounts, and the route below depends on that being true.

AccountScope, _extract_authentication_inputs and _resolve_account_id are a
seam, not an implementation — the final signature and dependency shape, so
routes can be written and tested against it now, while the credential
resolution described in design/boomerang-extension-auth-proposal.md lands
separately against a stable interface.

The /v1 prefix lives in exactly one place: the aggregator router in
app/routes/__init__.py. A route module declares @router.get("/me"), not
"/v1/me". Adding a route is then two edits in that package and none in
app.main, which includes the aggregator once and never needs touching again.

app.api.deps holds the database seam. The engine and session factory are built
in the FastAPI lifespan, next to bedrock.verify_config(), because that is what
runs once per Lambda cold start; a request arriving without lifespan startup
fails loudly rather than silently building an engine per request. DATABASE_URL
has no default in code and is rejected at startup if it is not the async
psycopg driver, for the same reason BEDROCK_MODEL has no default.

GET /v1/me takes no account id. The repository the handler receives is already
bound to the principal's account, so there is no id to read from the request
and no ownership check to forget. AccountProfile is an explicit response model
rather than the ORM row, because a column added to storage must not become a
response field by accident — google_subject is the case that matters: it is
stored, never exposed, and the only thing keeping it off the wire is that this
model does not list it.

/health stays outside /v1 and outside all of it, and requires no account,
lifespan or database, which is what makes it usable as a health check.

conftest.py gains the route fixtures, all scoped to a throwaway app through
FastAPI's own dependency_overrides — nothing under app/ ever installs one, so
none of this exists in a running process.

Folding the error envelope and the auth seam into the same change as the router
and the route means neither gets a review pass of its own: arguing with the
error contract on paper, before anything raises through it, now means arguing
with a diff that also wires the router and adds a route. It does resolve the
one objection a standalone version of this had — errors.py and auth.py used to
land reachable only from tests, with no production code path importing either.
Here app.main wires install_error_handling in the same commit that adds it.
```

---

### 06 — `feat/v1-item-detail-route`

**Commit / PR title:** `serve one return candidate's full detail at GET /v1/items/{item_id}`

```
serve one return candidate's full detail at GET /v1/items/{item_id}

The dashboard's detail view, and the first endpoint that derives anything rather
than returning what was stored.

Urgency is derived at render from return_by, and return_by goes on the wire as a
date. Never a countdown: "4 days left" computed on the server is frozen the moment
it is stored and silently wrong the next morning, which defeats the one thing this
product is for. When return_by is absent, urgency is unknown rather than a
default — the difference between "we do not know" and "you have plenty of time" is
the whole value of the field.

The next action follows a precedence table rather than a chain of conditionals, so
what the user is told to do next is one readable thing rather than an accumulation
of special cases. The policy's money and date columns are read through helpers
that respect the partial-column CHECK constraints — a value and its origin are
either both present or both absent, and the mapper rejects anything else.

A foreign item and a nonexistent item return byte-identical responses. Not the
same status code with a different message — identical bytes, asserted by a test.
Anything less makes the endpoint an existence oracle: an attacker with a valid
session enumerates ids and learns which ones exist in other accounts from the
shape of the failure. That property depends on not_found_error being the single
not-found constructor, and on the repository being account-scoped so the handler
never sees a foreign row to leak in the first place.

No account id is read from the request here either, for the same reason as /me.
```

---

## 9. Summary of what needs a human decision before execution

1. Confirm all three in-flight agents are finished, then re-verify §0.1 and §0.2.
2. Confirm `reviews/` as a new top-level directory is intended, and whether `AGENTS.md`'s repo map
   should gain a row for it in branch 2.
3. The PR-count decision is made: six branches, taking all three collapses in §6.4 (see the note at
   the top of this document and §6.5). Nothing in this stack is pending on that question anymore.
4. Accept that branch 4's (originally PR 6) greenness is asserted, not measured, in this document
   as written, and that the executor must stop there — per §5.2's isolated worktree gate, run after
   the commit — if that branch does not pass `make check` in isolation.
