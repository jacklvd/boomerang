# Boomerang — Implementation Plan

This plan breaks [`design/boomerang-low-level-design.md`](../design/boomerang-low-level-design.md)
into implementable tasks organized by execution batch. Tasks within a batch can be worked on
according to their track assignments. All tasks in a batch must complete before committing and
moving to the next batch.

**Total Tasks:** 91
**Batches:** 11 (Batch 0 through Batch 10), plus a deployment track
**Makespan under the batch barrier:** ~35 slots (20-task theoretical floor — see [Critical Path](#critical-path))
**Max Parallel Tracks:** 11 (in Batch 3)

> **This plan was revised on 2026-08-27** following an adversarial review. Twenty-five decisions —
> including the addition of Batch 0, the removal of FR-3.6.3 from scope, and three upstream
> amendments — are recorded with their reasoning in
> [`plan/boomerang-decisions.md`](boomerang-decisions.md). Read that document before questioning why
> a task exists. **`Dn` throughout this plan means a decision in that record** — not the `D1`–`D7`
> product decisions in [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md), which are a separate and
> older series.

---

## Reading this plan

**Batch 0 comes first and it is not code.** The largest named feasibility risk in this project —
high-level design §11 Q6, whether a free printable USPS label is reachable at all — was previously
unaddressed, and thirteen tasks were written against the assumption that it is. Batch 0 answers it
by hand, against a real account, with go/no-go criteria, before Batch 1 starts. It also files the
USPS API access request and measures Bedrock latency, because those are the two other numbers this
plan assumed rather than knew. See decisions D1–D5.

**Two workspaces, almost entirely independent.** `server/` (FastAPI, Python 3.13, `uv`) and
`extension/` (WXT, MV3, TypeScript, `bun`) share no files, no build, and no test runner. They meet
only at the wire contract of the seven endpoints — which is a *duplicated* type by design
(low-level design §3.5), not a shared module. So the server track and the extension track are
**truly parallel from Batch 1 to Batch 7**, and that is where nearly all the parallelism in this
plan lives.

**The duplication is checked, not trusted.** Two independently-written copies of a type that never
meet in a test can both be green and mutually incompatible. Task 3.18 creates `contracts/` — canonical
request and response JSON for every endpoint and one error body per reason code — and both suites
assert their serialization against those files. It is a shared *artifact*, deliberately not a shared
build step, so the parallelism above survives (decision D15).

**`client/` is out of scope, deliberately.** Low-level design §1 excludes it: phase 1 is a landing
page with no logic and phase 2 renders a list it does not compute. FR-3.6.2 therefore has no task
here and is recorded as an explicit gap in the traceability table rather than silently missing.

**FR-3.6.3 is cut from PoC scope.** The dashboard-to-extension messaging path needs a dashboard
hostname that does not exist (high-level design §11 Q1), and that hostname would otherwise block
Task 1.2 — the second task in the plan. The manifest declares no `externally_connectable` key, Task
5.6 routes internal messages only, and FR-3.6.3 joins FR-3.6.2 as a declared gap allowlisted in the
Task 10.2 sweep. See decision D6.

**Unit tests live inside their implementation task; integration tests are their own tasks.** The
§8.2 table is a per-module contract, and `implement-task-code` writes tests first — so splitting a
module from its unit rows would produce a task that cannot be executed under TDD at all. §8.3 rows
are different: they exercise a wired graph across several modules, so they depend on those modules
and get their own tasks. Test *infrastructure* — the fake browser, the fixture harness, the ASGI
app factory — is always its own task, because several tasks depend on it.

**`extension/` does not exist yet.** Task 1.2 creates it, alongside its own `AGENTS.md` as the
repo-level [`AGENTS.md`](../AGENTS.md) map already anticipates.

**`infra/` exists and is stale.** `infra/main.tf` still provisions a VPC, an internet gateway, an EC2
instance and security groups — the architecture the high-level design superseded. `infra/AGENTS.md`,
by contrast, is already correct: it documents the Lambda target state in full and quarantines the
old rules in a "Legacy scaffold" section it tells you to delete once the Lambda resources land. The
deployment track (Tasks I.1–I.3) is what lands them. It opens as soon as Task 6.5 exports the Mangum
handler and runs alongside Batches 7–10 rather than trailing them, so the first real deployment is
not also the last thing that happens. See decisions D7–D9.

---

## Package Dependency Graph

### Server — `server/app/`

```mermaid
graph TD
    ROUTES["routes"]
    SERVICES["services"]
    MODELS["models"]
    CARRIERS["carriers"]
    BEDROCK["bedrock"]
    PROMPTS["prompts"]
    ERRORS["errors"]
    CONFIG["config"]
    LOGGING["logging"]
    MIDDLEWARE["middleware"]
    DEPS["deps"]
    MAIN["main"]

    ROUTES --> SERVICES
    ROUTES --> MODELS
    ROUTES --> ERRORS
    ROUTES --> DEPS
    SERVICES --> CARRIERS
    SERVICES --> BEDROCK
    SERVICES --> MODELS
    SERVICES --> PROMPTS
    SERVICES --> ERRORS
    CARRIERS --> ERRORS
    CARRIERS --> MODELS
    BEDROCK --> CONFIG
    DEPS --> CONFIG
    DEPS --> ERRORS
    MIDDLEWARE --> LOGGING
    MAIN --> ROUTES
    MAIN --> MIDDLEWARE
    MAIN --> CARRIERS
    MAIN --> CONFIG
```

Layering rule from §2.1: **routes never call `carriers` or `bedrock` directly, and services never
import `fastapi`.** `middleware` is around the app rather than above routes, which is why nothing
calls into it.

### Extension — `extension/src/`

```mermaid
graph TD
    TYPES["src types"]
    CONFIG["src config"]
    EXTRACT["src extract"]
    ADAPTERS["src adapters"]
    VALIDATION["src validation"]
    STORAGE["src storage"]
    API["src api"]
    RANKING["src ranking"]
    CALENDAR["src calendar"]
    PERMISSIONS["src permissions"]
    MESSAGING["src messaging"]
    DRIVER["src driver"]
    CONTENT["entrypoints content"]
    BACKGROUND["entrypoints background"]
    POPUP["entrypoints popup"]

    STORAGE --> TYPES
    RANKING --> TYPES
    VALIDATION --> ADAPTERS
    API --> VALIDATION
    DRIVER --> VALIDATION
    DRIVER --> ADAPTERS
    DRIVER --> API
    DRIVER --> STORAGE
    DRIVER --> CALENDAR
    DRIVER --> EXTRACT
    MESSAGING --> STORAGE
    CONTENT --> EXTRACT
    BACKGROUND --> DRIVER
    BACKGROUND --> MESSAGING
    BACKGROUND --> API
    BACKGROUND --> VALIDATION
    BACKGROUND --> STORAGE
    BACKGROUND --> PERMISSIONS
    POPUP --> MESSAGING
    POPUP --> STORAGE
    POPUP --> PERMISSIONS
    POPUP --> RANKING
    POPUP --> CALENDAR
```

`src/types/` and `src/config.ts` are leaves that every module may import — §2.2's exemption. The
graph is otherwise **complete and prohibitive**: an edge not drawn is not permitted.

---

## Batch Execution Overview

```
Batch 0: Feasibility (BLOCKING, not code)
  Track A (serial): 0.1                              [spike]
  Track B (serial): 0.2                              [external dependency]
  Track C (serial): 0.3 (after 0.1)                  [measurement]
  --- 0.1 and 0.2 PARALLEL; 0.3 needs 0.1's captured subtree ---
  >>> Gate: go/no-go on the retailer flow, recorded in writing
  >>> Blocks 2.8, 3.13, 3.14, 7.7-7.10 and the Batch 9 driving rows ONLY

Batch 1: Workspace scaffolding
  Track A (serial): 1.1                              [server]
  Track B (serial): 1.2 -> 1.4                       [extension]
  Track C (serial): 1.3                              [repo CI]
  Track D (serial): 1.5 (after 1.2)                  [extension quality gates]
  --- Tracks A, B, C: PARALLEL (different workspaces) ---
  >>> Commit checkpoint: both workspaces build, run a green empty suite, and CI runs both

Batch 2: Foundations
  Track A (serial): 2.1                              [server errors]
  Track B (serial): 2.2                              [server config]
  Track C (serial): 2.3                              [server logging]
  Track D (serial): 2.4                              [extension types]
  Track E (serial): 2.5                              [extension config]
  Track F (serial): 2.6 -> 2.7                       [extension test fakes]
  Track G (serial): 2.8                              [extension fixtures]
  --- All tracks PARALLEL ---
  >>> Commit checkpoint: shared vocabulary and the fake browser exist

Batch 3: Schemas, protocols, leaf modules
  Track A (serial): 3.1 -> 3.2 -> 3.3 -> 3.4 -> 3.5  [server models and carrier protocol]
  Track B (serial): 3.6                              [server middleware]
  Track C (serial): 3.8                              [server deps]
  Track D (serial): 3.9 -> 3.10                      [extension extract]
  Track E (serial): 3.11                             [extension ranking]
  Track F (serial): 3.12                             [extension calendar]
  Track G (serial): 3.13 -> 3.14                     [extension adapters]
  Track H (serial): 3.17                             [extension permissions]
  Track I (deferred): 3.7                            [server window, after 3.2]
  Track J (deferred): 3.15 -> 3.16                   [extension validation, after 3.13]
  Track K (serial): 3.18                             [repo wire contract fixtures]
  --- Tracks A, B, C PARALLEL with D..K ---
  --- 3.7 CONFLICT-free but sequenced after 3.2 ---
  >>> Commit checkpoint: every boundary type exists on both sides, and both sides
  >>> assert against the same golden payloads

Batch 4: Model boundary, carriers, storage, egress
  Track A (serial): 4.2 -> 4.1                       [server bedrock and prompts]
  Track B (serial): 4.3 -> 4.4 -> 4.5                [server carriers usps]
  Track C (serial): 4.6 -> 4.7                       [extension storage core]
  Track C' (parallel after 4.7): 4.8, 4.9, 4.10, 4.11 -> 4.12   [extension repositories]
  Track D (serial): 4.13                             [extension api]
  Track E (serial): 4.14                             [server runtime mock carrier]
  --- Tracks A, B, E PARALLEL; C, D PARALLEL; server and extension PARALLEL ---
  --- 4.8-4.11 are now four separate files and run in parallel (D19) ---
  >>> Commit checkpoint: all persistence and all upstream clients exist

Batch 5: Services and driver collaborators
  Track A (serial): 5.1                              [server ingest]
  Track B (serial): 5.2                              [server action]
  Track C (serial): 5.3                              [server pickup]
  Track D (serial): 5.4 -> 5.5                       [extension driver collaborators]
  Track E (serial): 5.6                              [extension messaging]
  --- All tracks PARALLEL ---
  >>> Commit checkpoint: business logic is complete and unit-tested on both sides

Batch 6: Routes and app; driver core
  Track A (serial): 6.1 -> 6.2 -> 6.3 -> 6.4 -> 6.5  [server routes and main]
  Track B (serial): 6.6 -> 6.7 -> 6.8                [extension driver]
  --- Tracks A, B PARALLEL ---
  >>> Commit checkpoint: the server serves all seven endpoints; the driver drives
  >>> The deployment track opens here: I.1 -> I.2, then I.3 (needs 0.2's credentials)

Batch 7: Server integration tests; driver flows
  Track A (serial): 7.1                              [server integration harness]
  Track B (parallel after 7.1): 7.2, 7.3, 7.4, 7.5, 7.6
  Track C (serial): 7.7 -> 7.8 -> 7.9 -> 7.10        [extension driver flows]
  --- Tracks A/B PARALLEL with C ---
  >>> Commit checkpoint: the server is done and green; the return flow is complete

Batch 8: Entrypoints and wiring
  Track A (serial): 8.1 -> 8.2                       [extension worker and content]
  Track B (serial): 8.3 -> 8.4 -> 8.5                [extension popup]
  Gate (serial): 8.6 (after 8.5)                     [manual acceptance in a real browser]
  --- Tracks A, B CONFLICT-free but B depends on 8.2 for messaging ---
  >>> Commit checkpoint: the extension loads and runs end to end by hand,
  >>> observed in Chrome and not only under the fake browser

Batch 9: Extension integration tests
  Track A (serial): 9.1                              [harness]
  Track B (parallel after 9.1): 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
  >>> Commit checkpoint: every FR except the two declared gaps has a passing assertion

Batch 10: Build gates and repository checks
  Track A: 10.1    Track B: 10.2    Track C: 10.3
  --- All PARALLEL ---
  >>> Commit checkpoint: the pipeline built in 1.3 now enforces what review would otherwise have to

Deployment track (opens after 6.5, runs alongside Batches 7-10)
  I.1 -> I.2                                         [infra terraform, infra AGENTS.md]
  I.3 (after I.1, needs 0.2)                         [USPS sandbox reconciliation]
  >>> Not a batch: it has no barrier and blocks nothing downstream
```

---

## Batch 0: Feasibility

**This batch produces no application code.** It answers the three questions the rest of the plan
assumed the answers to: whether the retailer flow this product is built around actually exists,
whether we can get USPS credentials, and whether the model is fast enough for the latency budget
already written into the requirements. Decisions [D1–D5](boomerang-decisions.md#a-feasibility--the-risks-the-plan-started-without).

**What it blocks.** Tasks 2.8, 3.13, 3.14, 7.7–7.10, and the Batch 9 driving rows. It does **not**
block the server track, nor Tasks 1.2, 2.4, 2.5, 2.6 or 2.7 — a blocking spike that idles both
workspaces trades a risk reduction for a schedule loss.

---

### Track A: Retailer flow spike [spike]

#### Task 0.1: Walk the retailer return flow by hand and record what is there

**Prerequisites:** None
**Conflicts with:** None
**Parallel with:** Task 0.2
**Package:** `docs/spikes/`

**Objective:** Establish, against a real logged-in account on the PoC retailer, whether the product
this plan describes is buildable — before thirteen tasks are written against the assumption that it
is. High-level design §11 Q6 names this as the largest open feasibility risk and says in its own
words to prototype it before writing anything else in `extension/`.

**Three go/no-go criteria.** Each is answered yes or no, in writing, with the evidence that answered
it:

1. **A printable USPS label is reachable** through the return flow without leaving the browser and
   without a native app. If no: the pickup branch has nothing to attach to.
2. **Each offered return method's price is readable from the DOM** at the point of choice — not
   inferred, not behind a hover, not rendered into a canvas. If no: FR-3.3.4's "cheapest method"
   ranking cannot be computed and the driver has no basis for its recommendation.
3. **The printable label option is free.** If no: FR-3.3.5's assumption that the label path is the
   default recommendation is wrong, and the choice logic changes shape.

**Instructions:**
1. Using a real account with a real recent order, walk the return flow end to end in Chrome with
   DevTools open. Do not automate anything; this task is deliberately manual.
2. At each decision point, record: the URL, the DOM structure of the choice, whether prices are
   present as text, and what the "printable label" path actually produces (a PDF, a new tab, a
   download, a QR code only).
3. Answer each of the three criteria explicitly. **A criterion is "no" unless the evidence says
   yes** — an unchecked assumption records as a failure, not as a pass.
4. If any criterion fails, state what the PoC retargets to: a different retailer, a different return
   method, or a narrowed FR. Do not proceed to Batch 1 on a failed criterion without that decision
   written down.
5. Write the finding to `docs/spikes/retailer-flow.md`: the three answers, the evidence, the
   retailer and account conditions it was observed under, and the date. This document is what Task
   3.14 is built from.

**Verification:**
- `docs/spikes/retailer-flow.md` exists and answers all three criteria with evidence.
- If any answer is "no", the document names the retarget decision.

**Requirements covered:** — (validates the assumptions behind FR-3.3.4, FR-3.3.5, FR-3.4.1)

---

#### Task 0.2: File the USPS API access request

**Prerequisites:** None
**Conflicts with:** None
**Parallel with:** Task 0.1
**Package:** `docs/spikes/`

**Objective:** Start the one dependency in this plan whose latency is not ours to control. Tasks
4.3–4.5 build a USPS OAuth token provider and adapter; nothing in the original plan obtained
credentials, and third-party API approval has no stated turnaround.

**Instructions:**
1. Register for USPS APIs and request access to the OAuth token endpoint and the Carrier Pickup
   (Package Pickup) APIs the high-level design names.
2. Record in `docs/spikes/usps-access.md`: the date filed, the account used, the exact API products
   requested, and any stated turnaround.
3. **Do not block on the outcome.** Tasks 4.3–4.5 proceed against documentation-derived `respx`
   mocks (decision D12); Task I.3 reconciles them against the sandbox once credentials arrive.
4. When credentials arrive, store them in SSM under `/boomerang/<env>/usps/` — never in the
   repository, never in `.env` files that are not gitignored.

**Verification:**
- `docs/spikes/usps-access.md` records the request as filed with a date.

**Requirements covered:** — (unblocks FR-3.4.1, FR-3.4.5, FR-3.4.6 in production)

---

### Track C: Model latency [measurement]

#### Task 0.3: Measure Bedrock parse and action latency

**Prerequisites:** Task 0.1 (needs a captured DOM subtree to parse)
**Conflicts with:** None
**Parallel with:** —
**Package:** `docs/spikes/`

**Objective:** `BEDROCK_TIMEOUT_PARSE_MS = 9000` and `BEDROCK_TIMEOUT_ACTION_MS = 4500` are written
into the configuration table, and NFR-6.4 promises an action round trip under five seconds. High-level
design §11 Q9 records that none of this has been measured. Measure it before Batch 5 builds a service
against the number.

**Instructions:**
1. Write a throwaway script under `docs/spikes/` (not under `server/app/`) that uses the existing
   `server/app/bedrock.py` — `client()`, `model("parse")`, `model("action")` and `MAX_TOKENS` are
   already implemented, so this costs a script, not a subsystem.
2. Time a **cold** parse invoke and three **warm** parse invokes against a DOM subtree captured by
   Task 0.1, sanitised to the size ceiling `MAX_INGEST_BYTES` implies.
3. Time three **warm** action invokes against a representative action prompt.
4. Record p50 and max for each in `docs/spikes/bedrock-latency.md`, with the region, the model IDs
   resolved per call site, and the subtree size.
5. **Compare against the budgets.** If the measured action latency does not fit inside NFR-6.4's
   five-second round trip once network and server time are added, say so explicitly and raise it as
   an upstream amendment (decision D25) — either the timeout constants change or NFR-6.4 does. Do
   not silently proceed on a budget the measurement contradicts.

**Verification:**
- `docs/spikes/bedrock-latency.md` records p50 and max for cold parse, warm parse and warm action.
- The document states whether NFR-6.4's budget holds.

**Requirements covered:** — (validates NFR-6.4 and the §5.2 timeout constants)

---

### Batch 0 Gate

- [ ] All three criteria in `docs/spikes/retailer-flow.md` are answered with evidence
- [ ] Any failed criterion has a written retarget decision
- [ ] The USPS access request is filed and dated
- [ ] Bedrock latency is measured and reconciled against NFR-6.4
- [ ] Captured DOM subtrees are scrubbed per low-level design §9 Q1 and committed as the input to
      Task 2.8

---

## Batch 1: Workspace Scaffolding

### Track A: Server test harness [server]

#### Task 1.1: Reconcile the existing server test harness with the §8 layout

**Prerequisites:** None
**Conflicts with:** None
**Parallel with:** Task 1.2 (Track B — different workspace)
**Package:** `server`

**Objective:** `server/` was already scaffolded by `/setup-code-scaffolding` after this plan was
written, so this task **reconciles** rather than creates. Close the two genuine gaps — the missing
transport-level HTTP mock, and the flat `tests/` layout that does not match the §8 unit/integration
split — without recreating, overwriting, or downgrading any configuration that is already in place.

**What already exists — do not recreate, relax, or replace:**
- `server/pyproject.toml`: `[dependency-groups] dev` (`pytest>=8.4`, `pytest-asyncio>=1.2`,
  `pytest-cov>=7.0`, `mypy>=1.18`, `ruff>=0.14`, `pip-audit>=2.9`); `[tool.pytest.ini_options]` with
  `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["."]`, `--strict-markers`,
  `--strict-config`, `filterwarnings = ["error"]`; `[tool.ruff]` with `select = ["ALL"]` and a
  documented ignore list; `[tool.mypy]` strict with `mypy_path = "."` and
  `explicit_package_bases = true`; `[tool.coverage]` with `branch = true` and `fail_under = 95`.
- `server/Makefile` (`install test cov lint fmt fmt-check typecheck audit check setup-hooks`),
  `server/AGENTS.md`, the repo-root `.husky/pre-commit` dispatcher, `scripts/pre-commit-server.sh`,
  and `scripts/setup-hooks.sh`.
- `server/tests/`: a flat `conftest.py`, `test_main.py`, `test_bedrock.py` — 19 passing tests,
  `make check` green at 100% coverage.

**Instructions:**
1. Add **`respx`** to `server/pyproject.toml` under `[dependency-groups] dev` — the only genuinely
   missing dependency. §8.1 requires transport-level mocking rather than client-object
   monkeypatching, and nothing in the scaffolding provides it. Add it with `uv add --dev respx` (or
   the equivalent edit plus `uv lock`); do not touch any other entry in the group, and do not
   re-pin what is already there. `anyio` is not needed: async already runs through `pytest-asyncio`
   in `asyncio_mode = "auto"`.
2. Adopt the §8 layout: `server/tests/unit/` and `server/tests/integration/`, and create
   `server/tests/__init__.py`, `server/tests/unit/__init__.py`,
   `server/tests/integration/__init__.py`. **These `__init__.py` files are required, not optional.**
   The plan names four colliding test basenames across directories — `test_orders.py`,
   `test_returns.py` and `test_pickups.py` in both `tests/unit/models/` and `tests/unit/routes/`
   (Tasks 3.2/3.3/3.4 vs. 6.2/6.3/6.4), and `test_ingest.py` in both `tests/unit/services/` and
   `tests/integration/` (Task 6.1 vs. Task 7.2). Without `__init__.py`, pytest's rootdir-relative
   module naming raises `import file mismatch` on the second file of each pair. Later tasks that
   add a new subdirectory under `tests/unit/` (`models/`, `routes/`, `services/`, `carriers/`,
   `prompts/`) must add an `__init__.py` to it for the same reason.
3. **`# dev-note:` and follow-up — the scaffolding's config comments become wrong.** Step 2 reverses
   a deliberate scaffolding decision, so the executor of this task must also correct the two places
   that record the old stance, in the same change:
   - `server/pyproject.toml`, `[tool.ruff.lint.per-file-ignores]`: the `"tests/*"` entry ignores
     `INP001` with the comment `# tests/ is intentionally not a package`. That comment is now false
     and the ignore is now dead. Replace the entry's comment with the reason it changed — `tests/` is
     a package because the §8 layout puts colliding basenames in sibling directories — or drop the
     `INP001` line entirely, and leave the rest of the ignore list untouched.
   - `server/pyproject.toml`, `[tool.mypy]`: the `# dev-note:` above `mypy_path` and
     `explicit_package_bases` states that `tests/` has no `__init__.py`. Rewrite that note to say
     what is now true. Keep `mypy_path = "."` and `explicit_package_bases = true` — they are
     harmless with packages and removing them is a downgrade this task has no reason to make.
4. **Move, never copy, the two existing test files:** `git mv server/tests/test_main.py
   server/tests/unit/test_main.py` and `git mv server/tests/test_bedrock.py
   server/tests/unit/test_bedrock.py` (Task 4.6 already verifies `tests/unit/test_bedrock.py`). A
   split brain in which `tests/test_main.py` and `tests/unit/test_errors.py` both exist passes every
   gate while being permanently inconsistent, so the flat files must not survive the move. Confirm
   with `git status` that each shows as a rename and that nothing is left directly under `tests/`
   except `conftest.py` and the two package directories.
5. **Keep the existing `conftest.py` and add to it — do not replace it.** `server/tests/conftest.py`
   already defines the autouse `clean_bedrock_env` fixture that clears `BEDROCK_MODEL`,
   `BEDROCK_MODEL_PARSE`, `BEDROCK_MODEL_ACTION` and `AWS_REGION` and resets `bedrock.client`'s
   cache; that fixture stays exactly as it is, at `tests/conftest.py`, so both `unit/` and
   `integration/` inherit it. Do **not** add an `anyio_backend` fixture — `asyncio_mode = "auto"`
   already selects the backend, and a redundant fixture would imply an anyio dependency the suite
   does not have. Add a `# dev-note:` recording that this file is a shared-conflict point that many
   later tasks append to (Task 7.1 adds the `app` fixture here).
6. Do **not** add a placeholder "the package imports" test: the suite is already non-empty and green.
7. Reference: Low-Level Design §8.1 (test approach), §8.5 (what is not tested); `server/AGENTS.md`.

**Verification:**
- `cd server && uv sync` — resolves with `respx` added and nothing else changed.
- `cd server && uv run python -c "import respx"` — the new dependency is installed.
- `cd server && make test` — the same 19 tests still pass from their new locations.
- `cd server && make check` — `fmt-check`, `lint`, `typecheck`, `cov` (95% line + branch floor) and
  `audit` all pass; ruff must not report `INP001` after step 3.
- `cd server && uv run pytest tests/unit` — collects the moved tests.
- `cd server && git status --short` — shows two renames, not two additions, and no stray file left
  directly under `server/tests/`.

**Requirements covered:** —

---

### Track B: Extension workspace [extension]

#### Task 1.2: WXT project scaffold and MV3 manifest

**Prerequisites:** None
**Conflicts with:** None
**Parallel with:** Task 1.1 (Track A — different workspace)
**Package:** `extension`

**Objective:** Create the `extension/` workspace with WXT, TypeScript, vitest and the MV3 manifest, and assert the manifest's permission posture in a test.

**Instructions:**
1. Create `extension/` with `package.json` (bun, matching the repo's toolchain), `tsconfig.json`
   (strict), `wxt.config.ts`, and `vitest.config.ts`.
2. In `wxt.config.ts`, declare the manifest:
   - `permissions: ["activeTab", "scripting", "storage"]` — **nothing else at install**.
   - `optional_host_permissions` for the retailer origins (requested later, in context).
   - An explicit extension CSP with no remote script.
   - No `unlimitedStorage`.
   - **No `externally_connectable` key.** FR-3.6.3 is cut from PoC scope (decision D6): the
     dashboard origin it would name does not exist, and requiring it here would block the second
     task in the plan on an undecided hostname.
   - Leave a `// dev-note:` at the `manifest` declaration recording that the `key` field is added by
     Task 1.4, so a reader does not conclude it was forgotten.
3. Add `extension/AGENTS.md` following the pattern of `server/AGENTS.md`: local scope, phase, and the
   subset of the repo rules that bite hardest here — rules 8 and 9 from the repo
   [`AGENTS.md`](../AGENTS.md), and "the extension must never hold a carrier or retailer credential."
4. Add `extension/tests/manifest.test.ts` asserting, against the built manifest object:
   - the permission array is exactly the three above;
   - no `<all_urls>` appears anywhere in the manifest;
   - **`externally_connectable` is absent** — this is the assertion that keeps the D6 cut from
     silently reverting when someone copies a manifest from a tutorial.
5. Create empty `extension/src/` and `extension/entrypoints/` directories with a `.gitkeep`.
6. Reference: Low-Level Design §7.2 (manifest), §8.2 (manifest assertions); requirements FR-3.7.1,
   NFR-6.5; repo `AGENTS.md` rule 8; decision D6.

**Verification:**
- `cd extension && bun install && bun run build` — WXT produces `.output/chrome-mv3/`.
- `cd extension && bun run test` — the manifest test passes.

**Requirements covered:** FR-3.7.1 (partial — completed by Task 1.4), NFR-6.5

---

#### Task 1.4: Generate and pin the extension keypairs

**Prerequisites:** Task 1.2
**Conflicts with:** Task 1.2 (both edit `wxt.config.ts`)
**Parallel with:** Tasks 1.1, 1.3
**Package:** `extension`

**Objective:** Fix the extension ID. Without a pinned public `key` in the manifest, Chrome derives
the extension ID from the absolute path the unpacked extension was loaded from — so the ID differs
between every machine and every CI run. NFR-6.5 allowlists **exactly one** `chrome-extension://`
origin on the Lambda Function URL, a literal string that must be known at `terraform apply` time.
FR-3.7.1 requires the pin; requirements line 761 states the consequence of omitting it. Decision D20.

**Why this is in Batch 1.** The derived origin is an *input* to the CORS policy Task I.1 writes — it
has to exist before the thing that allowlists it. It also makes the ID stable for every unpacked
load from this point forward, which everything depending on a stable ID needs.

**Instructions:**
1. Generate two RSA keypairs — one `dev`, one `prod`:
   `openssl genrsa -out dev.pem 2048` and the same for `prod.pem`.
2. Derive each public key in the base64 DER form the manifest `key` field takes, and derive the
   resulting extension ID from it.
3. Put the **dev public key** in `wxt.config.ts` as `manifest.key`. Public keys are not secrets and
   belong in the repository — that is the entire point of pinning one.
4. **Neither private key enters the repository.** Store both at
   `/boomerang/release/<env>/extension-key` in SSM as SecureStrings per high-level design §8.4, in
   the same account but outside the path the Lambda execution role can read. Hold the prod private
   key additionally offline. Add `*.pem` to `extension/.gitignore` in this task, not later.
5. Record both derived extension IDs in `extension/AGENTS.md` — Task I.1 needs the dev ID for the
   CORS allowlist and Task 10.1 needs to know which key is the dev one.
6. Extend `extension/tests/manifest.test.ts`: the built manifest has a `key` field, and it is a
   non-empty string. Assert the *presence*, not the value — the value changes between dev and prod
   builds and a pinned literal would fail the prod build for the wrong reason.
7. Reference: requirements FR-3.7.1 and NFR-6.5; high-level design §8.4; decision D20.

**Note on the prod keypair.** It only earns its place if Boomerang self-packages a CRX — a Chrome
Web Store listing would issue the identity instead. High-level design §8.4's per-environment SSM
path assumes self-packaging, and Task 10.1's dev-key scan is meaningless with only one key, so both
are generated. If the project later commits to store distribution, drop the prod key and the
corresponding half of Task 10.1 together.

**Verification:**
- `cd extension && bun run build` — the built manifest contains a `key`.
- The extension ID is identical when loaded unpacked from two different directories.
- `git status` — no `.pem` file is tracked; `grep -r "PRIVATE KEY" .` finds nothing in the repo.
- `cd extension && bun run test` — the manifest test asserts `key` is present.

**Requirements covered:** FR-3.7.1, NFR-6.5

---

### Track C: Repository CI [repo]

#### Task 1.3: Continuous integration for both workspaces

**Prerequisites:** None
**Conflicts with:** None
**Parallel with:** Tasks 1.1, 1.2
**Package:** `.github/`

**Objective:** Batch 10's commit checkpoint claims that "CI enforces what review would otherwise
have to." There is no `.github/` directory and, before this task, nothing created one — so three
Batch 10 tasks wrote checks that would never have run. Create the pipeline at the *start* of the
project rather than the end. Decision D10.

**Why Batch 1 and not Batch 10.** A gate added at the end tells you the last commit was clean. A gate
added at the start tells you which commit broke it. Batch 10's tasks then add checks to an existing
pipeline instead of inventing one.

**Instructions:**
1. Create `.github/workflows/ci.yml` triggered on push and pull request.
2. **Server job:** set up Python 3.13 and `uv`, run `cd server && make check` — which already covers
   `fmt-check`, `lint`, `typecheck`, `cov` at the 95% line-and-branch floor, and `audit`.
3. **Extension job:** set up `bun`, run `bun install`, `bun run build`, `bun run test`, `bun run lint`.
4. **Repo job:** run `scripts/citation-sweep.sh` **if it exists** — Task 10.2 creates it. Write the
   step so an absent script skips rather than fails, and leave a `# dev-note:` saying that Task 10.2
   makes it real. A hard failure here would block every commit until Batch 10.
5. Write both workspace jobs to **discover** their workspace rather than hard-code a file list, so
   tasks that add modules do not also have to edit CI.
6. Jobs run in parallel; the workflow fails if any fails.

**Verification:**
- Push a branch: both jobs run and pass against the Batch 1 state of the repository.
- Deliberately break a lint rule in each workspace and confirm the corresponding job fails.

**Requirements covered:** — (mechanism for NFR-6.3; the gate Tasks 10.1–10.3 attach to)

---

### Track D: Extension quality gates [extension]

#### Task 1.5: Extension coverage floor and pre-commit hook

**Prerequisites:** Task 1.2
**Conflicts with:** None
**Parallel with:** Tasks 1.1, 1.3, 1.4
**Package:** `extension`, `.husky/`

**Objective:** The server enforces `fail_under = 95` with `branch = true`. The extension had no
coverage gate at all — and the most intricate logic in this plan, the driver state machine, lives
there. The repo's `.husky/pre-commit` is likewise server-only, so every extension task in this plan
could be committed without running a test. Decisions D13, D14.

**Instructions:**
1. In `extension/vitest.config.ts`, enable coverage with a **95% line and 95% branch** floor across
   `extension/src/`.
2. Exclude `extension/entrypoints/` from the floor using an **explicit named list of files**, not a
   glob. A glob silently swallows anything later dropped into the directory; a named list makes each
   exclusion a reviewable line. Entrypoints are covered by the Batch 9 integration rows instead.
   Add a `// dev-note:` at the list saying exactly that, and add each entrypoint to the list in the
   task that creates it (8.1, 8.2, 8.3).
3. Extend `.husky/pre-commit` — today a server-only dispatcher — to run the extension workspace's
   tests and lint when files under `extension/` are staged. Follow the existing dispatcher pattern
   and add `scripts/pre-commit-extension.sh` beside `scripts/pre-commit-server.sh`.
4. Reference: `server/pyproject.toml` `[tool.coverage]` for the standard being matched; decisions
   D13, D14.

**Verification:**
- `cd extension && bun run test --coverage` — reports coverage and enforces the floor.
- Staging a change under `extension/` runs the extension checks in the hook; staging only server
  files does not.

**Requirements covered:** — (mechanism for NFR-6.3)

---

### Batch 1 Commit Checkpoint

After all tracks complete:
- [ ] Server installs and tests run: `cd server && uv run pytest`
- [ ] Extension builds: `cd extension && bun run build`
- [ ] Extension tests run: `cd extension && bun run test`
- [ ] The extension ID is pinned and stable across machines; no private key is tracked
- [ ] CI runs both workspaces on push and fails on a deliberate break
- [ ] Both workspaces have a place to put test-first code, and the manifest posture is now guarded
      by an assertion rather than by memory.

---

## Batch 2: Foundations

### Track A: Server error taxonomy [server]

#### Task 2.1: `app/errors.py` — the exception hierarchy

**Prerequisites:** Task 1.1
**Conflicts with:** None
**Parallel with:** Tasks 2.2, 2.3, 2.4–2.8
**Package:** `server/app`

**Objective:** Define the one exception base every service raises, with each subclass carrying its
`reason` string and HTTP status as class attributes, so the wire contract of §4.2 cannot drift.

**Instructions:**
1. Create `server/app/errors.py` with `BoomerangError(Exception)` carrying class-level `reason: str`
   and `status: int`, plus an optional `detail` for the log (never the response body).
2. Subclass one per reason in the **closed** table of requirements §4.2 — and only those:
   `unrecognized-page`, `wrong-carrier-label`, `address-not-serviceable`, `location-not-serviceable`,
   `etag-expired`, `upstream-unavailable`, `payload-too-large`, `label-not-printed`, `client-too-old`.
   The list is closed: a failure that fits none of these is one of these, not a tenth reason.
3. Each class carries `reason`, `status`, and a `message` — one sentence a human can act on — plus an
   optional `details` mapping that is **absent** by default. `location-not-serviceable` is its one
   occupant, carrying `details.servable_locations`: the reduced set FR-3.4.8 requires the user be
   re-asked from, because substituting a location on their behalf is forbidden.
4. `address-not-serviceable` is an error **only** on the schedule path. FR-3.4.1 makes a negative
   eligibility answer a *successful* response carrying that same reason in the normal result body, so
   the eligibility route must never raise this class — one endpoint, one body shape. `# dev-note:`
   this on the class itself; it is the single most inviting mistake in the file.
5. The reason string, status and message live on the class and nowhere else. A `# dev-note:` should
   say why: the response body is generated from the class, so adding a reason means adding a class.
6. Unit tests (`tests/unit/test_errors.py`): every subclass has a non-empty distinct `reason`; every
   `reason` matches `^[a-z]+(-[a-z]+)*$` (kebab-case, per §4.2); `details` is absent unless the class
   documents it; the set of reasons matches the documented table exactly (assert against a literal
   list in the test, so both an undocumented addition and a quiet removal fail).
7. Reference: Low-Level Design §6.1, §6.2; requirements §4.2, FR-3.4.1, FR-3.4.8.

**Verification:**
- `cd server && uv run pytest tests/unit/test_errors.py`

**Requirements covered:** §4.2, FR-3.4.1, FR-3.4.8, NFR-6.3

---

### Track B: Server configuration [server]

#### Task 2.2: `app/config.py` — `Settings` and fail-fast validation

**Prerequisites:** Task 1.1
**Conflicts with:** None
**Parallel with:** Tasks 2.1, 2.3, 2.4–2.8
**Package:** `server/app`

**Objective:** Load every environment variable from requirements §5.1/§5.2 into one validated
`Settings` object that refuses to construct when a required value is missing or malformed.

**Instructions:**
1. Create `server/app/config.py` with a pydantic-settings `Settings` model covering the full §5.1
   table: Bedrock model ids per call site, region, max tokens, USPS credentials and base URL, the
   allowed CORS origins, the minimum supported client version, upstream timeouts and the request
   deadline, the payload ceiling, and the log level.
2. **No defaults for anything a wrong value would silently break** — follow the existing
   `app/bedrock.py` precedent, which deliberately gives `BEDROCK_MODEL` no default and names
   `ListInferenceProfiles` in the failure message. Timeouts and ceilings may have defaults; identity,
   endpoints and version floors may not.
3. Provide `get_settings()` with `lru_cache` — one instance per warm container (§5.1).
4. Validators: origins parse to a non-empty list of absolute origins; the minimum client version
   parses as a version; timeouts are positive; the payload ceiling is positive and below the
   Function URL body limit.
5. Unit tests: each required variable missing raises, and the message names the variable; a malformed
   origin list raises; `get_settings()` returns the same object twice.
6. Reference: Low-Level Design §7.1; requirements §5.1, §5.2.

**Verification:**
- `cd server && uv run pytest tests/unit/test_config.py`

**Requirements covered:** §5.1, NFR-6.5, NFR-6.6, NFR-6.7

---

### Track C: Server logging [server]

#### Task 2.3: `app/logging.py` — redacting formatter and request-id binding

**Prerequisites:** Task 1.1
**Conflicts with:** None
**Parallel with:** Tasks 2.1, 2.2, 2.4–2.8
**Package:** `server/app`

**Objective:** Make the logger structurally incapable of emitting page content or carrier
credentials, and give every log line the request id.

**Instructions:**
1. Create `server/app/logging.py` with a `request_id` `ContextVar` and `bind_request_id(value)`.
2. Implement a JSON formatter that emits **only an allowlist** of fields. §6.2 is explicit that this
   is an allowlist, not a denylist — a new field is invisible until it is added, which is the safe
   direction. Add a `# dev-note:` saying so.
3. Fields: timestamp, level, logger, message, `request_id`, and a bounded `extra` whose keys are
   themselves allowlisted (e.g. `reason`, `endpoint`, `status`, `duration_ms`, `retailer_key`).
4. Never log: extracted DOM, order contents, addresses, tracking numbers, USPS credentials, Bedrock
   prompt or completion bodies.
5. Unit tests: a record carrying a payload field emits without it; a record with an allowlisted extra
   emits with it; the request id appears when bound and is absent (not `null`-crashing) when not;
   two concurrent tasks binding different ids do not see each other's (this is the contextvar
   isolation §8.3 later exercises end to end).
6. Reference: Low-Level Design §6.2; requirements NFR-6.3.

**Verification:**
- `cd server && uv run pytest tests/unit/test_logging.py`

**Requirements covered:** §4.2, NFR-6.1

---

### Track D: Extension shared vocabulary [extension]

#### Task 2.4: `src/types/` — entities, session, and the state enums

**Prerequisites:** Task 1.2
**Conflicts with:** None
**Parallel with:** Tasks 2.1–2.3, 2.5–2.8
**Package:** `extension/src/types`

**Objective:** Define every persisted entity and cross-module type in one leaf module that everything
may import and that imports nothing.

**Instructions:**
1. Create `extension/src/types/` with the entity types from §3.5: `Order`, `OrderItem`,
   `ReturnRequest`, `Pickup`, `Address`, `BookedAddress`, `DriverSession`, `RankedItem`,
   `ProposedAction`, `ValidatedAction` (constructor-private — see Task 3.15), `ReturnMethodOption`.
2. `DriverSession` carries exactly: `state`, `item_id`, `order_id`, `retailer_key`, `tab_id`,
   `tab_url`, `step_key`, `chosen_option`, `attempt_count`, `started_at`, `last_written_at`,
   `schema_version`. `chosen_option` is nullable — the free-drop-off branch never makes a choice.
   Carry §3.5's rationale into a `// dev-note:`: it exists because the worker dies between the choice
   and the label page, and a value held only in memory across two transitions is sometimes not there.
3. Define the FR-3.3.9 return state union: `AwaitingLabelChoice`, `Driving`, `LabelReady`,
   `AwaitingConfirm`, `Stalled`, and the four terminals `LabelPrinted`, `DroppedOff`, `HandedOff`,
   `Aborted`. Define the pickup state union including the read-time-derived `Abandoned` and
   `Collected`.
4. Define `ActionKind` as a closed union of exactly `click`, `select_option`, `fill`,
   `pause_for_user`, `report_stuck` — the extension's mirror of the server's enum.
5. Every persisted type carries `schema_version`.
6. Unit tests: type-level tests are cheap here — add a `expectTypeOf`/`assertType` suite pinning
   `ActionKind` to five members and the terminal set to four, so widening either fails the build.
7. Reference: Low-Level Design §3.5; requirements FR-3.3.9, FR-3.3.5.

**Verification:**
- `cd extension && bun run test tests/types` and `bunx tsc --noEmit`

**Requirements covered:** FR-3.3.5, FR-3.3.8, FR-3.3.9

---

### Track E: Extension build-time config [extension]

#### Task 2.5: `src/config.ts` — build-time constants

**Prerequisites:** Task 1.2
**Conflicts with:** None
**Parallel with:** Tasks 2.1–2.4, 2.6–2.8
**Package:** `extension/src`

**Objective:** Put every value that differs between dev and prod behind WXT's define substitution, so
a dev value in a prod bundle is a build-time fact rather than a runtime surprise.

**Instructions:**
1. Create `extension/src/config.ts` exporting the constants from §7.2: `API_BASE_URL`,
   `CLIENT_VERSION`, `MODEL_FALLBACK_TIMEOUT_MS`, `MAX_INGEST_BYTES`, `STORAGE_CAP_BYTES`,
   `STORAGE_EVICTION_MARGIN_BYTES`, `API_REQUEST_TIMEOUT_MS`, `API_RETRY_BUDGET_MS`,
   `RETURN_ATTEMPT_LIMIT`.
   - **These names are normative and were previously wrong here.** `PAYLOAD_CEILING_BYTES` and
     `API_TIMEOUT_MS` appear nowhere in the requirements or the low-level design; the real names are
     `MAX_INGEST_BYTES` and `API_REQUEST_TIMEOUT_MS`. `API_RETRY_BUDGET_MS` is specified upstream and
     was missing from this plan entirely, so the retry budget it governs would not have been built.
     Decision D17.
   - `DASHBOARD_ORIGIN` is **not** exported: FR-3.6.3 is cut from PoC scope (decision D6) and nothing
     consumes it.
2. Wire the environment-varying ones through WXT `define` in `wxt.config.ts` so they are substituted
   at build time, not read at runtime.
3. Unit tests: each constant is defined and of the right type; the numeric ones are positive; the
   eviction margin is smaller than the cap; **`API_RETRY_BUDGET_MS` is greater than or equal to
   `API_REQUEST_TIMEOUT_MS`** — a retry budget smaller than a single attempt's timeout can never
   permit a retry, which is a configuration bug that otherwise shows up as an unexplained absence of
   retries in production.
4. Reference: Low-Level Design §7.2; requirements §5.1, §5.2; decisions D6, D17.

**Verification:**
- `cd extension && bun run test tests/config.test.ts`

**Requirements covered:** §5.1, NFR-6.4

---

### Track F: Extension fake browser [extension]

#### Task 2.6: Fake `chrome.storage.local`

**Prerequisites:** Task 1.2
**Conflicts with:** Task 2.7 (both add to `extension/tests/fakes/chrome.ts`)
**Parallel with:** Tasks 2.1–2.5, 2.8
**Package:** `extension/tests/fakes`

**Objective:** Build a storage double that reproduces the three properties §8.1 says the real API has
and that the design depends on — per-`set` atomicity, a hard quota, and a `getBytesInUse` consistent
with what was written.

**Instructions:**
1. Create `extension/tests/fakes/chrome-storage.ts` implementing `get`, `set`, `remove`, `clear`,
   `getBytesInUse` over an in-memory map.
2. **Atomicity:** a single `set` with several keys either applies wholly or not at all. Interleaving
   two `set` calls must be observable in tests, because §4.3's whole reason for existing is that
   `chrome.storage.local` gives no multi-key transaction.
3. **Quota:** expose `armQuotaRejection()` so a test can make the next `set` fail the way the real
   API does, and make `getBytesInUse` reflect the *pre-failure* state afterwards.
4. `getBytesInUse` must be computed from the serialized values, not stubbed — the eviction logic in
   Task 4.12 measures with it and would pass against a lying double.
5. Unit tests for the fake itself: a rejected `set` leaves no partial write; `getBytesInUse` grows
   and shrinks with writes and removes.
6. Reference: Low-Level Design §8.1, §4.3, §5.2.

**Verification:**
- `cd extension && bun run test tests/fakes/chrome-storage.test.ts`

**Requirements covered:** —

---

#### Task 2.7: Fake `tabs`, `scripting`, `permissions`, worker lifecycle, and clock

**Prerequisites:** Task 2.6
**Conflicts with:** Task 2.6 (both add to `extension/tests/fakes/chrome.ts`)
**Parallel with:** Tasks 2.1–2.5, 2.8
**Package:** `extension/tests/fakes`

**Objective:** Complete the fake browser with the surfaces the driver and permission flow touch, plus
the two doubles that make the design's hardest tests possible: worker termination and a controllable
clock.

**Instructions:**
1. `extension/tests/fakes/chrome-tabs.ts` — `create`, `update`, `get`, `remove`, `onRemoved`, with a
   settable current URL and a way to close a tab so `TabHandle.is_live` goes false.
2. `extension/tests/fakes/chrome-scripting.ts` — `executeScript` returning a DOM string a test
   supplies per tab and step.
3. `extension/tests/fakes/chrome-permissions.ts` — `contains`, `request` (grant or deny per test),
   `remove`, and a gesture flag so a `request` outside a gesture can be made to fail the way the real
   API does.
4. `extension/tests/fakes/worker-lifecycle.ts` — a `WorkerLifecycle` double with `terminate()` that
   discards **all** in-memory state and forces the next call to go through rehydration. This is the
   double that makes §8.3's two worker-death rows meaningful; if it does not actually drop memory,
   both rows pass vacuously.
5. `extension/tests/fakes/clock.ts` — an injectable clock, since §8.5 rules out sleeping in tests and
   §3.5's `first_seen_at` / window derivation are time-dependent.
6. Assemble `extension/tests/fakes/chrome.ts` composing all of the above into one `globalThis.chrome`
   installer with a `reset()`.
7. Unit tests for the fakes: terminate loses memory but not storage; a permission request outside a
   gesture rejects; a closed tab reports not live.
8. Reference: Low-Level Design §8.1, §4.4, §3.4.

**Verification:**
- `cd extension && bun run test tests/fakes`

**Requirements covered:** —

---

### Track G: Extension DOM fixtures [extension]

#### Task 2.8: Retailer DOM fixture harness

**Prerequisites:** Task 1.2, **Task 0.1** (supplies the captured subtrees)
**Conflicts with:** None
**Parallel with:** Tasks 2.1–2.7
**Package:** `extension/tests/fixtures`

**Objective:** Establish where captured retailer pages live, how they are scrubbed, and how a test
loads one — the convention §9 Q1 leaves open and every adapter test depends on.

**Instructions:**
1. Create `extension/tests/fixtures/retailers/{retailer_key}/{step_key}.html` as the layout, populated
   with the **real subtrees Task 0.1 captured and scrubbed** — one directory for the PoC retailer, one
   file per step the spike actually walked. This is not a placeholder harness: the spike navigated
   those pages, so the fixtures are real DOM rather than invented markup, and Task 3.14's selectors
   are written against pages that exist (decision D2).
2. Write `extension/tests/fixtures/load.ts` exposing `load_fixture(retailer_key, step_key)` returning
   a parsed DOM.
3. Write `extension/tests/fixtures/README.md` fixing the **scrubbing convention**, which is the part
   that matters: real names, addresses, order numbers, tracking numbers, emails and any auth token
   are replaced with stable synthetic values before a capture is committed. State that a fixture is
   committed only after scrubbing, and that scrubbing is manual and reviewed — this closes §9 Q1 with
   a written answer rather than an implicit one.
4. Add a fixture lint test: no committed fixture matches the tracking-number or postal-address
   patterns from Task 3.10 except in the synthetic forms the README declares. This makes the
   convention enforced rather than aspirational.
5. Reference: Low-Level Design §8.1, §9 Q1.

**Verification:**
- `cd extension && bun run test tests/fixtures`

**Requirements covered:** NFR-6.1, NFR-6.3

---

### Batch 2 Commit Checkpoint

After all tracks complete:
- [ ] Server tests pass: `cd server && uv run pytest`
- [ ] Extension type-checks and tests pass: `cd extension && bunx tsc --noEmit && bun run test`
- [ ] The server has its error taxonomy, validated settings, and a redacting logger.
- [ ] The extension has its shared type vocabulary, its build-time constants, a fake browser that can
      kill a worker and reject a quota, and a fixture convention with a lint behind it.

---

## Batch 3: Schemas, Protocols, Leaf Modules

### Track A: Server request and response models [server]

#### Task 3.1: `app/models/common.py` — strict base model and the error body

**Prerequisites:** Task 2.1
**Conflicts with:** Tasks 3.2, 3.3, 3.4 (all re-export through `app/models/__init__.py`)
**Parallel with:** Tasks 3.6, 3.8, 3.9–3.17
**Package:** `server/app/models`

**Objective:** Establish the strictness every wire model inherits, so an unexpected field is a 422
rather than a silently ignored one.

**Instructions:**
1. Create `server/app/models/common.py` with a `StrictModel` base: `model_config` sets
   `extra="forbid"`, `str_strip_whitespace=True`, and `frozen=True` where the model is a value.
2. Define bounded string types (max lengths) used across the payloads — the ceiling is enforced at
   the boundary, not by trusting the client.
3. Define `ErrorBody` with exactly the §4.2 shape and nothing more:
   ```python
   reason: str        # kebab-case code from the closed table
   message: str       # one sentence a human can act on
   request_id: str    # the opaque per-request correlator, not a session id
   details: dict | None = None   # omitted from the JSON when absent
   ```
   plus `from_error(err: BoomerangError, request_id: str) -> ErrorBody`. Serialisation must **omit**
   `details` rather than emit `null` — the documented default is absent.
4. Unit tests: an extra field raises; an over-long string raises; `from_error` produces the documented
   shape for a sample of subclasses; a class with no `details` serialises to exactly three keys; the
   `location-not-serviceable` class serialises `details.servable_locations`.
5. Reference: Low-Level Design §3.1, §6.2; requirements §4.2.

**Verification:**
- `cd server && uv run pytest tests/unit/models/test_common.py`

**Requirements covered:** §4.2, NFR-6.1

---

#### Task 3.2: `app/models/orders.py` — ingestion payloads

**Prerequisites:** Task 3.1
**Conflicts with:** Tasks 3.1, 3.3, 3.4 (`app/models/__init__.py`)
**Parallel with:** Tasks 3.6, 3.8, 3.9–3.17
**Package:** `server/app/models`

**Objective:** Model the extraction payload the extension sends and the parsed orders the server
returns.

**Instructions:**
1. Create `server/app/models/orders.py`: `IngestRequest` (retailer key, page URL, extracted content,
   captured-at instant), `OrderItemSchema`, `OrderSchema`, `IngestResponse`.
2. Enforce the payload ceiling on the extracted content field — the request is rejected with
   `payload-too-large` before any model call. The ceiling comes from `Settings`, so accept it as a
   validation context rather than hardcoding.
3. `OrderSchema` carries the fields FR-3.2.1 needs for window derivation: order date,
   delivery date if known, item identity, and the retailer's stated return policy window if present.
4. Unit tests: a payload one byte over the ceiling raises; a well-formed payload round-trips; a
   missing required order field raises.
5. Reference: Low-Level Design §3.1, §4.1; requirements FR-3.1.4, FR-3.2.1, §4.1.

**Verification:**
- `cd server && uv run pytest tests/unit/models/test_orders.py`

**Requirements covered:** FR-3.1.3, FR-3.1.4, FR-3.2.1

---

#### Task 3.3: `app/models/returns.py` — `ActionKind` and `ProposedAction`

**Prerequisites:** Task 3.1
**Conflicts with:** Tasks 3.1, 3.2, 3.4 (`app/models/__init__.py`)
**Parallel with:** Tasks 3.6, 3.8, 3.9–3.17
**Package:** `server/app/models`

**Objective:** Define the closed action vocabulary as one enum, and the proposed-action model whose
per-kind field rules make a malformed action unconstructable.

**Instructions:**
1. Create `server/app/models/returns.py` with `ActionKind` as a `StrEnum` of exactly five members:
   `click`, `select_option`, `fill`, `pause_for_user`, `report_stuck`.
2. Add a `# dev-note:` recording that **this enum is the single source the tool schema's `enum` is
   generated from** (Task 4.1) — the two must never be written out twice, because a divergence is
   exactly the hole repo rule 9 exists to close.
3. `ProposedAction` with per-kind validation: `click` requires a selector and nothing else;
   `select_option` requires selector plus option; `fill` requires selector plus value; `pause_for_user`
   requires a reason string and no selector; `report_stuck` requires a reason and no selector.
   Cross-field validation rejects any other combination.
4. `NextStepRequest` (retailer key, step key, page content, prior action outcome, fillable field
   descriptors) and `NextStepResponse` (the `ProposedAction`).
5. Unit tests: `len(ActionKind) == 5` asserted literally; a `fill` without a value raises; a `click`
   with a value raises; an action kind outside the enum raises.
6. Reference: Low-Level Design §3.1, §4.2; requirements FR-3.3.8; repo `AGENTS.md` rule 9.

**Verification:**
- `cd server && uv run pytest tests/unit/models/test_returns.py`

**Requirements covered:** FR-3.3.8

---

#### Task 3.4: `app/models/pickups.py` — address, eligibility, schedule, refresh, cancel

**Prerequisites:** Task 3.1
**Conflicts with:** Tasks 3.1, 3.2, 3.3 (`app/models/__init__.py`)
**Parallel with:** Tasks 3.6, 3.8, 3.9–3.17
**Package:** `server/app/models`

**Objective:** Model the four pickup endpoints, including the one field the architecture forbids
storing and the one it requires.

**Instructions:**
1. Create `server/app/models/pickups.py`: `Address`, `EligibilityRequest`, `EligibilityResult`
   (serviceable flag plus the carrier's own reason), `ScheduleRequest`, `ScheduledPickup`
   (`confirmation_number`, the address it was booked against, the **day** USPS named),
   `RefreshedPickup`, `CancelRequest`.
2. **`ScheduledPickup` has no `ETag` field, and must not gain one.** Add a `# dev-note:` citing repo
   `AGENTS.md` rule 3: the ETag is good for one hour or one use, so cancellation refreshes to obtain
   a current one rather than replaying a stored one. The absence of the field is the enforcement.
3. **No time-window field either** — a day, never a window (rule 5). Name the field for a day and
   type it as a date, so a window cannot be smuggled into it.
4. `ScheduleRequest` requires the carrier whose postage is on the box (rule 4) — scheduling is gated
   on that, not on "a label exists."
5. Unit tests: `ScheduledPickup` rejects an `etag` field (it is `extra="forbid"`, so this is a real
   assertion); the day field rejects a datetime range; a `ScheduleRequest` without the postage
   carrier raises.
6. Reference: Low-Level Design §3.1, §4.3; requirements FR-3.4.1–FR-3.4.8, §4.1; repo `AGENTS.md`
   rules 3, 4, 5.

**Verification:**
- `cd server && uv run pytest tests/unit/models/test_pickups.py`

**Requirements covered:** FR-3.4.3, FR-3.4.5, FR-3.4.5a, FR-3.4.8

---

#### Task 3.5: `app/carriers/base.py` — the `CarrierAdapter` protocol

**Prerequisites:** Task 3.4
**Conflicts with:** None
**Parallel with:** Tasks 3.6, 3.8, 3.9–3.17
**Package:** `server/app/carriers`

**Objective:** Define the carrier seam as a `Protocol` so the service layer depends on a shape, and
the scripted double in Task 4.5 and the runtime stub in Task 4.14 are peers of the real adapter
rather than patches over it.

**Instructions:**
1. Create `server/app/carriers/__init__.py` and `server/app/carriers/base.py`.
2. Define `CarrierAdapter` as a `typing.Protocol` with the four operations — check eligibility,
   schedule, refresh, cancel — plus servable-locations lookup, all `async`, all typed against the
   Task 3.4 models.
3. Every method's contract note says which `BoomerangError` subclass it may raise; the protocol is
   where that is written down, because two implementations must agree on it.
4. Unit tests: a deliberately incomplete stub fails a `runtime_checkable` structural check, pinning
   the method set.
5. Reference: Low-Level Design §3.2, §2.1.

**Verification:**
- `cd server && uv run pytest tests/unit/carriers/test_base.py`

**Requirements covered:** FR-3.4.1, FR-3.4.8, NFR-6.3

---

### Track B: Server middleware [server]

#### Task 3.6: `app/middleware.py` — request id

**Prerequisites:** Task 2.3
**Conflicts with:** None
**Parallel with:** Tasks 3.1–3.5, 3.8–3.17
**Package:** `server/app`

**Objective:** Generate or accept a request id per request, bind it for the duration, and return it on
the response.

**Instructions:**
1. Create `server/app/middleware.py` with an ASGI middleware that reads an inbound request-id header
   if present and well-formed, otherwise generates one; binds it via `bind_request_id`; sets it on the
   response header; and resets the contextvar on the way out.
2. Resetting matters on Lambda: the container is reused, so a leaked contextvar would attach the
   previous invocation's id to the next one.
3. Unit tests: an inbound id is echoed; an absent id yields a generated one; a malformed inbound id is
   replaced rather than trusted; the contextvar is clear after the response.
4. Reference: Low-Level Design §6.2, §7.1.

**Verification:**
- `cd server && uv run pytest tests/unit/test_middleware.py`

**Requirements covered:** §4.2, NFR-6.1

---

### Track C: Server dependencies and version gate [server]

#### Task 3.8: `app/deps.py` — app-state accessors and the client version gate

**Prerequisites:** Task 2.1, Task 2.2
**Conflicts with:** None
**Parallel with:** Tasks 3.1–3.6, 3.9–3.17
**Package:** `server/app`

**Objective:** Provide the FastAPI dependencies routes use to reach settings and the carrier adapter,
and the version gate that rejects an unsupported client **before** any model or carrier call.

**Instructions:**
1. Create `server/app/deps.py` with `get_settings_dep` and `get_carrier_adapter` reading from
   `request.app.state` — the objects are constructed once in `main.py` (Task 6.5), not per request.
2. Implement `require_supported_client` as a dependency: parse **`X-Boomerang-Client-Version`**,
   compare to `Settings.min_client_version`, raise `UnsupportedClientVersion` if below or absent.
   - **The header name is normative and comes from requirements §4.1.** Neither this task nor Task
     4.13 named it before; since §4.2 specifies that an *absent* header raises `client-too-old`, two
     independently-written tasks choosing different spellings would produce a system where every
     request from the real client is rejected — and both unit suites would pass. Task 3.18's golden
     payloads carry the header so the two sides are checked against one string. Decision D16.
3. **The gate runs before the handler body.** §8.3 asserts on two endpoints that no upstream call
   happens on rejection, so it must be a dependency, not a first line inside each handler.
4. Unit tests: a version below the floor raises; an absent header raises; a version at the floor
   passes; a malformed version raises rather than being treated as new; **a header spelled any other
   way is treated as absent** — this is the assertion that catches a divergence from §4.1.
5. Reference: Low-Level Design §3.3, §7.1; requirements §4.1 (header name), §4.2 (`client-too-old`),
   §5.1; decision D16.

**Verification:**
- `cd server && uv run pytest tests/unit/test_deps.py`

**Requirements covered:** §4.2 (`client-too-old`), §5.1

---

### Track I: Server window derivation [server]

#### Task 3.7: `app/services/window.py` — return-window derivation and urgency

**Prerequisites:** Task 3.2
**Conflicts with:** None
**Parallel with:** Tasks 3.6, 3.8, 3.9–3.17
**Package:** `server/app/services`

**Objective:** Derive each item's return deadline from the order and policy facts, as a pure function
of its inputs and an injected instant.

**Instructions:**
1. Create `server/app/services/__init__.py` and `server/app/services/window.py` with
   `derive_window(order, item, now)` returning the deadline and the basis it was derived from.
2. Handle the precedence FR-3.2.1 sets out: an explicit retailer-stated deadline wins; then a
   policy window measured from the delivery date; then from the order date; and when none of them is
   available, return an **undetermined** result rather than guessing a default window.
3. `now` is a parameter. No `datetime.now()` inside — §8.5 rules out sleeping and §8.2 tests this
   across boundary dates.
4. Unit tests: each precedence branch; the undetermined branch; day-boundary behaviour; an item whose
   deadline has already passed.
5. Reference: Low-Level Design §3.3, §4.1; requirements FR-3.2.1, FR-3.2.2.

**Verification:**
- `cd server && uv run pytest tests/unit/services/test_window.py`

**Requirements covered:** FR-3.2.1, FR-3.2.2

---

### Track D: Extension extraction and egress scan [extension]

#### Task 3.9: `src/extract/` — subtree selection and sanitisation

**Prerequisites:** Task 2.4, Task 2.5, Task 2.8
**Conflicts with:** Task 3.10 (both export from `src/extract/index.ts`)
**Parallel with:** Tasks 3.1–3.8, 3.11–3.17
**Package:** `extension/src/extract`

**Objective:** Turn a live order page into the bounded, script-free text the server is allowed to see.

**Instructions:**
1. Create `extension/src/extract/extract.ts` with `extract(document, adapter)`:
   - select the subtree the adapter names, not the whole document;
   - strip `<script>`, `<style>`, inline event handlers, and `data:` URIs;
   - normalise whitespace;
   - truncate at `MAX_INGEST_BYTES` (requirements §5.1) measured in **bytes, not characters**.
2. Truncation must be deterministic and must not split a multi-byte character.
3. Unit tests, using Task 2.8 fixtures: a page with inline handlers loses them; a page over the
   ceiling comes back exactly at or under it; the same page extracts identically twice; a page whose
   subtree is missing yields an explicit empty result rather than falling back to `document.body`.
4. Reference: Low-Level Design §3.4, §4.1; requirements FR-3.1.2, FR-3.1.4, NFR-6.3.

**Verification:**
- `cd extension && bun run test tests/extract/extract.test.ts`

**Requirements covered:** FR-3.1.2, FR-3.1.4

---

#### Task 3.10: `src/extract/` — the fail-closed egress scan

**Prerequisites:** Task 3.9
**Conflicts with:** Task 3.9 (`src/extract/index.ts`)
**Parallel with:** Tasks 3.1–3.8, 3.11–3.17
**Package:** `extension/src/extract`

**Objective:** Provide the pure predicate that decides whether a fallback payload contains a tracking
number or a postal address — the check, and only the check.

**Instructions:**
1. Create `extension/src/extract/egress-scan.ts` exporting `scan_for_pii(text): ScanResult`.
2. Patterns: carrier tracking-number formats (USPS, UPS, FedEx) and US postal-address shapes.
3. **This module decides nothing about what to do with a hit.** §3.4 splits ownership deliberately:
   `src/extract/` owns the scan, `src/driver/` owns the consequence. Add a `// dev-note:` saying so,
   because the natural instinct is to abort right here and that would put policy in a matcher.
4. Fail closed: wrap the whole scan so that **a throw counts as flagged**. A scanner that crashes on
   an odd input must not read as "clean".
5. Unit tests, table-driven: one row per pattern with a positive and a near-miss negative; an input
   that makes the matcher throw returns flagged; an empty string is clean.
6. Reference: Low-Level Design §3.4, §4.2; requirements FR-3.1.3, NFR-6.3.

**Verification:**
- `cd extension && bun run test tests/extract/egress-scan.test.ts`

**Requirements covered:** FR-3.1.3, NFR-6.1

---

### Track E: Extension ranking [extension]

#### Task 3.11: `src/ranking/` — urgency ordering

**Prerequisites:** Task 2.4
**Conflicts with:** None
**Parallel with:** Tasks 3.1–3.10, 3.12–3.17
**Package:** `extension/src/ranking`

**Objective:** Order items by return-window urgency, as a pure function of the items and an injected
instant.

**Instructions:**
1. Create `extension/src/ranking/rank.ts` with `rank(items, now): RankedItem[]`.
2. Soonest deadline first; items whose window is undetermined sort after dated ones rather than being
   dropped; expired items are labelled expired and sorted last.
3. **Stable ordering** — two items with the same deadline keep their input order. §8.2 tests this
   explicitly because the popup re-renders and a jittering list reads as a bug.
4. `now` is a parameter, no clock reads inside.
5. Unit tests: ordering across mixed deadlines; ties preserve input order; undetermined placement;
   expired placement; an empty list.
6. Reference: Low-Level Design §3.4; requirements FR-3.2.3.

**Verification:**
- `cd extension && bun run test tests/ranking`

**Requirements covered:** FR-3.2.2, FR-3.2.3

---

### Track F: Extension calendar [extension]

#### Task 3.12: `src/calendar/` — template URL and `.ics`

**Prerequisites:** Task 2.4, Task 2.5
**Conflicts with:** None
**Parallel with:** Tasks 3.1–3.11, 3.13–3.17
**Package:** `extension/src/calendar`

**Objective:** Produce a calendar reminder as a pre-filled template URL and as a downloadable `.ics`,
with **no OAuth scope of any kind**.

**Instructions:**
1. Create `extension/src/calendar/template-url.ts` building the Google Calendar template URL with
   correctly encoded title, details and date.
2. Create `extension/src/calendar/ics.ts` generating a valid single-`VEVENT` `.ics` with CRLF line
   endings, proper escaping of commas and semicolons in text fields, and line folding at 75 octets.
3. Add a `// dev-note:` on both: this exists because of repo `AGENTS.md` rules 1 and 2 — the template
   URL and the `.ics` are the *reason* the product holds no Google scope, and a task that seems to
   need one has misread the design.
4. Both are pure functions; neither performs navigation or a download — the popup does that.
5. Unit tests: URL encoding of a title containing `&` and spaces; `.ics` escaping of a comma in the
   summary; folding of a long description; the generated `.ics` parses; the date is rendered in the
   expected form.
6. Reference: Low-Level Design §3.4; requirements FR-3.5.1; repo `AGENTS.md` rules 1, 2.

**Verification:**
- `cd extension && bun run test tests/calendar`

**Requirements covered:** FR-3.5.1, FR-3.5.2, FR-3.5.3, FR-3.5.4

---

### Track G: Extension retailer adapters [extension]

#### Task 3.13: `src/adapters/` — adapter type and registry

**Prerequisites:** Task 2.4
**Conflicts with:** Task 3.14 (both export from `src/adapters/index.ts`)
**Parallel with:** Tasks 3.1–3.12, 3.15–3.17
**Package:** `extension/src/adapters`

**Objective:** Define what a retailer adapter is and how one is found, before any concrete adapter
exists.

**Instructions:**
1. Create `extension/src/adapters/types.ts` with the `RetailerAdapter` shape from §3.4:
   `retailer_key`, URL matchers for order pages and return pages, the extraction subtree selector,
   per-step selector maps, `fillable_fields` (the allowlist `fill` is bounded by),
   `carrier_by_option`, `label_carrier_patterns`, and the return-method-option reader.
2. Create `extension/src/adapters/registry.ts` with `for_url(url)` and `for_key(key)`.
3. `for_url` returns `null` on no match — it never guesses a nearest adapter.
4. Unit tests: a registered URL resolves; an unregistered one returns null; `for_key` on an unknown
   key returns null; two adapters cannot register the same key.
5. Reference: Low-Level Design §3.4, §2.2; requirements FR-3.1.1.

**Verification:**
- `cd extension && bun run test tests/adapters/registry.test.ts`

**Requirements covered:** FR-3.1.1

---

#### Task 3.14: The PoC retailer adapter

**Prerequisites:** Task 3.13, Task 2.8
**Conflicts with:** Task 3.13 (`src/adapters/index.ts`)
**Parallel with:** Tasks 3.1–3.12, 3.15–3.17
**Package:** `extension/src/adapters`

**Objective:** Implement one retailer end to end — the PoC scope is one retailer complete, not two
halfway.

**Instructions:**
1. Create `extension/src/adapters/{retailer_key}/index.ts` implementing `RetailerAdapter` against the
   fixtures from Task 2.8.
2. Populate `carrier_by_option` — the mapping from each offered return method to the carrier whose
   postage that method puts on the box. This is **source one** of FR-3.3.5's derivation.
3. Populate `label_carrier_patterns` — patterns matched **locally, on the label page, and never
   transmitted**. Add a `// dev-note:` recording the never-transmitted part.
4. Populate `fillable_fields` with the allowlist of inputs `fill` may target. No password, payment or
   file-upload input may appear in it (repo rule 9); add an assertion in the test rather than only a
   comment.
5. Unit tests, per fixture: each step's selectors resolve against its fixture; the return-method
   option reader returns every option with its price; an option whose price is unreadable comes back
   marked unreadable rather than as zero or free.
6. Reference: Low-Level Design §3.4, §4.6; requirements FR-3.3.1, FR-3.3.4, FR-3.3.5.

**Verification:**
- `cd extension && bun run test tests/adapters`

**Requirements covered:** FR-3.1.1, FR-3.3.4, FR-3.3.5, FR-3.3.7

---

### Track J: Extension validation [extension]

#### Task 3.15: `src/validation/` — the action validator

**Prerequisites:** Task 2.4, Task 3.13
**Conflicts with:** Task 3.16 (both export from `src/validation/index.ts`)
**Parallel with:** Tasks 3.1–3.12, 3.17
**Package:** `extension/src/validation`

**Objective:** Make `ValidatedAction` a type that can only come into existence through this module, so
"was this checked?" is answered by the type rather than by discipline.

**Instructions:**
1. Create `extension/src/validation/action.ts` with `validate_action(proposed, adapter):
   ValidatedAction | ValidationRejection`.
2. `ValidatedAction` carries a private brand — no other module can construct one. Add a
   `// dev-note:` explaining that this is the whole point: `StepExecutor` accepts only
   `ValidatedAction`, so an unvalidated action is a compile error rather than a runtime check
   somebody forgot.
3. Checks: the kind is one of the five; per-kind field rules match Task 3.3's server-side rules; for
   `fill`, the target selector must appear in the adapter's `fillable_fields` — an unknown target is
   rejected, not attempted.
4. Rejections carry a reason the driver can log and act on; the validator never throws for a
   malformed action.
5. Unit tests: each of the five kinds validates in its correct shape; a `fill` at a target outside
   `fillable_fields` rejects; a `fill` at a password-typed field in the fixture rejects; a sixth
   invented kind rejects; a `click` carrying a value rejects; `ValidatedAction` cannot be constructed
   outside the module (a type-level test).
6. Reference: Low-Level Design §3.4, §4.2; requirements FR-3.3.8; repo `AGENTS.md` rule 9.

**Verification:**
- `cd extension && bun run test tests/validation/action.test.ts`

**Requirements covered:** FR-3.3.8

---

#### Task 3.16: `src/validation/` — the order response validator

**Prerequisites:** Task 2.4
**Conflicts with:** Task 3.15 (`src/validation/index.ts`)
**Parallel with:** Tasks 3.1–3.12, 3.17
**Package:** `extension/src/validation`

**Objective:** Validate server responses at the boundary, so a malformed or hostile response never
reaches storage as an entity.

**Instructions:**
1. Create `extension/src/validation/order.ts` validating the ingest response into `Order` /
   `OrderItem`, and the pickup responses into `Pickup` / `BookedAddress`.
2. Unknown fields are dropped, not stored; missing required fields reject the whole response rather
   than producing a half entity.
3. Unit tests: a well-formed response validates; an extra field is dropped; a missing required field
   rejects; a wrong-typed date rejects; a response containing an `etag` field is dropped without it
   ever entering an entity (rule 3, enforced at the boundary too).
4. Reference: Low-Level Design §3.4, §5.1; requirements NFR-6.3, NFR-6.5.

**Verification:**
- `cd extension && bun run test tests/validation/order.test.ts`

**Requirements covered:** NFR-6.3, NFR-6.5

---

### Track H: Extension permissions [extension]

#### Task 3.17: `src/permissions/` — two-tier permission state

**Prerequisites:** Task 2.4, Task 2.7
**Conflicts with:** None
**Parallel with:** Tasks 3.1–3.16
**Package:** `extension/src/permissions`

**Objective:** Model the two-tier posture — `activeTab` plus a gesture first, a standing host
permission offered afterwards — as queryable state, with the request confined to the popup.

**Instructions:**
1. Create `extension/src/permissions/permissions.ts` with `has_standing(origin)`,
   `request_standing(origin)`, `revoke_standing(origin)`, and `register_listeners()` for
   `onAdded`/`onRemoved`.
2. `request_standing` must be callable **only from the popup**. Add a guard that throws if invoked
   from the worker, plus a `// dev-note:` recording why: `chrome.permissions.request` requires a user
   gesture and the service worker has none, so a worker-side call fails at runtime — the guard turns
   that into an immediate, legible failure.
3. `has_standing` never requests. Query and request are separate calls so no code path can acquire a
   permission as a side effect of asking about one.
4. Unit tests against the Task 2.7 fake: query returns false before and true after a grant; a denied
   request leaves the state false and does not throw; a request from a non-popup context throws; a
   revocation is observed by the listener.
5. Reference: Low-Level Design §3.4, §7.2; requirements FR-3.7.2, FR-3.7.3; repo `AGENTS.md` rule 8.

**Verification:**
- `cd extension && bun run test tests/permissions`

**Requirements covered:** FR-3.3.2, FR-3.7.2, FR-3.7.3

---

### Track K: Wire contract fixtures [repo]

#### Task 3.18: `contracts/` — golden payloads both sides assert against

**Prerequisites:** Task 3.4 (server models complete), Task 3.16 (extension response validators)
**Conflicts with:** None
**Parallel with:** Tasks 3.6–3.17
**Package:** `contracts/`

**Objective:** This plan's preamble states that the wire types are *"a duplicated type by design"*.
Duplication is a legitimate choice — it is what keeps the two workspaces parallel from Batch 1 to
Batch 7 — but nothing verified the two copies agree. The server's Pydantic model and the extension's
TypeScript interface never meet in a test, so both suites can be green on mutually incompatible
shapes and the first evidence would be a broken request in a real browser. Decision D15.

**Why golden files rather than code generation.** Codegen would couple the two workspaces' builds and
destroy the parallelism that is this plan's main asset. Golden JSON is a shared *artifact*, not a
shared *build step*: each side reads the files independently at test time, and a divergence fails a
test on whichever side drifted. Batches 1–7 stay parallel.

**Instructions:**
1. Create `contracts/` at the repository root — not inside either workspace, because it belongs to
   neither.
2. For each of the seven endpoints in requirements §4.1, write a canonical request body and a
   canonical success response body as JSON, named `contracts/{endpoint}/request.json` and
   `contracts/{endpoint}/response.json`. Use realistic values, not `"string"` placeholders — a
   fixture that no serializer would ever produce cannot catch a type error.
3. Write one error body per reason code in requirements §4.2 — all nine, each with the mandatory
   `request_id` — as `contracts/errors/{reason}.json`.
4. Requests carry the `X-Boomerang-Client-Version` header value alongside the body, so both sides are
   checked against one spelling of the header Task 3.8 and Task 4.13 must agree on (decision D16).
5. Write `contracts/README.md` stating the rule: **these files are the contract; a change to either
   side that requires changing a file here is a wire-breaking change** and must be made deliberately,
   in its own commit, touching both workspaces.
6. **Server side:** a test that parses each request fixture into its Pydantic model without error, and
   serializes each model to a body that equals the response fixture. Add it to
   `server/tests/unit/test_contracts.py`.
7. **Extension side:** a test that type-checks each response fixture against its interface and passes
   it through the Task 3.16 validators, and that each request the client builds matches the request
   fixture. Add it to `extension/tests/contracts.test.ts`.
8. **The failure mode this exists to catch:** rename a field on one side only, and exactly one of the
   two suites must go red. Verify that by doing it before declaring the task complete.
9. Reference: requirements §4.1, §4.2; low-level design §3.5; decision D15.

**Verification:**
- `cd server && uv run pytest tests/unit/test_contracts.py`
- `cd extension && bun run test tests/contracts.test.ts`
- Temporarily rename a field in `app/models/orders.py` — the server contract test fails and the
  extension one does not; revert.

**Requirements covered:** §4.1, §4.2

---

### Batch 3 Commit Checkpoint

After all tracks complete:
- [ ] Server tests pass: `cd server && uv run pytest`
- [ ] Extension type-checks and tests pass: `cd extension && bunx tsc --noEmit && bun run test`
- [ ] Every wire type exists on both sides of the boundary, and every leaf module the driver and the
      popup will consume is implemented and unit-tested.
- [ ] Both sides assert against the same golden payloads in `contracts/`, so the duplicated wire
      types can no longer drift silently.
- [ ] `ValidatedAction` is unconstructable outside the validator, and the egress scan fails closed.

---

## Batch 4: Model Boundary, Carriers, Storage, Egress

### Track A: Server model boundary [server]

#### Task 4.2: `app/bedrock.py` — settings-driven client and per-call-site models

**Prerequisites:** Task 2.2
**Conflicts with:** Task 4.1 (both are the model boundary; 4.1 imports from this module)
**Parallel with:** Tasks 4.3–4.5 (Track B), 4.6–4.13 (extension)
**Package:** `server/app`

**Objective:** Rework the existing `app/bedrock.py` scaffold to read from `Settings` rather than
`os.getenv`, keeping its two existing virtues — per-call-site model ids and a startup verification.

**Instructions:**
1. Modify `server/app/bedrock.py`. It already has `CALL_SITES = ("parse", "action")`,
   `_require_model`, `model`, `verify_config`, and an `lru_cache`'d `client()`. Keep that shape.
2. Replace direct `os.getenv` reads with `get_settings()`. Keep the property that a missing model id
   raises with a message naming `ListInferenceProfiles` — it is the actual next step for whoever hits
   it, and losing that costs a real debugging session.
3. Keep `client()` cached at module scope: on Lambda the warm container should reuse the client and
   its credential cache (§5.2).
4. Add `invoke_with_tool(call_site, system, messages, tool)` performing a **forced tool choice** call
   and returning the tool input, raising `ModelUnavailable` on transport failure and `ParseUnusable`
   when the model returns no tool use.
5. Unit tests with an `httpx.MockTransport`: a forced tool call returns the tool input; a transport
   error raises `ModelUnavailable`; a text-only completion raises `ParseUnusable`; `verify_config`
   raises when a call site's model id is unset; `client()` returns the same object twice.
6. Reference: Low-Level Design §3.3, §5.2, §7.1; requirements §5.1.

**Verification:**
- `cd server && uv run pytest tests/unit/test_bedrock.py`

**Requirements covered:** NFR-6.3, NFR-6.6

---

#### Task 4.1: `app/prompts/` — tool schemas generated from the enums

**Prerequisites:** Task 4.2, Task 3.2, Task 3.3
**Conflicts with:** Task 4.2
**Parallel with:** Tasks 4.3–4.5, 4.6–4.13
**Package:** `server/app/prompts`

**Objective:** Build the two tool schemas — order extraction and next action — deriving the action
schema's `enum` from `ActionKind` rather than restating it.

**Instructions:**
1. Create `server/app/prompts/__init__.py`, `server/app/prompts/parse.py`,
   `server/app/prompts/action.py`.
2. The action tool schema's `enum` is `[k.value for k in ActionKind]` — **generated, never typed
   out**. Add a `# dev-note:` recording that a hand-written duplicate is the one way repo rule 9's
   guarantee could quietly fail.
3. Per-kind property requirements in the schema mirror Task 3.3's `ProposedAction` validation.
4. The parse tool schema targets `OrderSchema`.
5. System prompts state the closed vocabulary and that the page content is untrusted data, never
   instruction.
6. Unit tests: the action schema's enum equals the five `ActionKind` values, asserted by comparing to
   the enum itself and separately to a literal list (so a change to either side is caught); the
   schema validates a sample of each valid action and rejects an invented kind; the parse schema
   accepts a well-formed order object.
7. Reference: Low-Level Design §3.3, §4.1, §4.2; requirements FR-3.3.8; repo `AGENTS.md` rule 9.

**Verification:**
- `cd server && uv run pytest tests/unit/prompts`

**Requirements covered:** FR-3.1.4, FR-3.3.8

---

### Track B: Server USPS carrier [server]

#### Task 4.3: `app/carriers/usps/token.py` — OAuth token provider

**Prerequisites:** Task 2.1, Task 2.2
**Conflicts with:** Tasks 4.4, 4.5 (`app/carriers/usps/__init__.py`)
**Parallel with:** Tasks 4.1–4.2, 4.6–4.13
**Package:** `server/app/carriers/usps`

**Objective:** Fetch, cache and refresh the USPS OAuth token in the warm container, with a safety
margin before expiry.

**Instructions:**
1. Create `server/app/carriers/usps/__init__.py` and `token.py` with a `TokenProvider` holding the
   current token and its expiry.
2. `get_token()` returns the cached token when it has more than a refresh margin of life left, and
   otherwise fetches a new one. Concurrent callers during a refresh must not each trigger a fetch —
   guard with an `asyncio.Lock`.
3. A token fetch failure raises `CarrierUnavailable`. The credentials come from `Settings` and are
   never logged (Task 2.3's allowlist already makes that structural, but do not pass them as an
   `extra` either).
4. Unit tests with `httpx.MockTransport`: a fresh token is fetched once and reused; a token inside the
   margin triggers a refresh; two concurrent `get_token()` calls produce one fetch; a 401 from the
   token endpoint raises `CarrierUnavailable`; the token never appears in a log record.
5. Reference: Low-Level Design §3.2, §5.2; requirements §5.2, NFR-6.3.

**Verification:**
- `cd server && uv run pytest tests/unit/carriers/test_token.py`

**Requirements covered:** NFR-6.5, NFR-6.6

---

#### Task 4.4: `app/carriers/usps/adapter.py` — `UspsAdapter`

**Prerequisites:** Task 4.3, Task 3.5, Task 3.4
**Conflicts with:** Tasks 4.3, 4.5 (`app/carriers/usps/__init__.py`)
**Parallel with:** Tasks 4.1–4.2, 4.6–4.13
**Package:** `server/app/carriers/usps`

**Objective:** Implement `CarrierAdapter` against the real USPS API — the four pickup operations plus
servable locations — translating carrier failures into the error taxonomy.

**Instructions:**
1. Create `server/app/carriers/usps/adapter.py` implementing all five protocol methods, each using
   `TokenProvider` and an `httpx.AsyncClient` with the timeout from `Settings`.
2. `check_eligibility` returns a serviceable/not-serviceable result **including USPS's own reason**;
   not-serviceable is a normal result, not an exception (a meaningful share of users get a no).
3. `schedule` returns the `confirmation_number`, the address booked against, and **the day USPS
   named in its own response** — not tomorrow, not a computed guess. A `# dev-note:` should cite rule
   5 and the 2 AM Central cutoff / Saturday-evening cases as the reason the day is read rather than
   derived.
4. `refresh` returns the current pickup **and its fresh ETag as a return value only** — never
   persisted, never in a response model (Task 3.4 has no field for it). `cancel` takes the ETag it
   was just handed by a refresh.
5. Error translation: HTTP 401 after a valid token → `CarrierUnavailable`; a location refusal →
   `LocationRefused`; an already-collected pickup → `AlreadyCollected`; a timeout →
   `UpstreamTimeout`; anything unrecognised → `CarrierUnavailable` with the detail logged, never the
   raw body returned.
6. Unit tests with `httpx.MockTransport`, one per branch above, plus: the day in the response is the
   day USPS returned even when it is not tomorrow; the ETag never appears in the returned model.
7. Reference: Low-Level Design §3.2, §4.3, §6.1; requirements FR-3.4.1–FR-3.4.7; repo `AGENTS.md`
   rules 3, 5.

**Verification:**
- `cd server && uv run pytest tests/unit/carriers/test_usps_adapter.py`

**Requirements covered:** FR-3.4.1, FR-3.4.3, FR-3.4.5, FR-3.4.6, FR-3.4.8

---

#### Task 4.5: `app/carriers/usps/scripted.py` — `ScriptedUspsAdapter`

**Prerequisites:** Task 3.5, Task 3.4
**Conflicts with:** Tasks 4.3, 4.4 (`app/carriers/usps/__init__.py`)
**Parallel with:** Tasks 4.1–4.2, 4.6–4.14
**Package:** `server/app/carriers/usps`

**Objective:** Provide the scriptable adapter every server integration test drives, as a peer
implementation of the protocol rather than a patch.

**This class was called `MockUspsAdapter` and the rename is the point.** Requirements §5.1 makes
`CARRIER_ADAPTER=mock` the *runtime* default until USPS access lands, so "the mock" also names the
adapter a running deployment uses — and a strict push/pop double cannot serve one: the first real
request pops an empty queue and raises. Two different objects were sharing one name. This task builds
the **test double**; Task 4.14 builds the **runtime stub**. Decision D21.

**Instructions:**
1. Create `server/app/carriers/usps/scripted.py` with `ScriptedUspsAdapter` implementing
   `CarrierAdapter`.
2. `push(method, outcome)` queues an outcome per method; each call pops the next queued outcome for
   that method. An outcome is either a value or an exception to raise.
3. Calling a method with an empty queue is an **error**, not a default — a test that did not say what
   should happen must fail rather than silently receive a happy path. Do **not** add a permissive
   mode for runtime use; that is Task 4.14's job, and a mode flag here would put the silent happy
   path one constructor argument away from every test.
4. Provide `assert_drained()` for teardown: a queued outcome that no call consumed means the test did
   not exercise what it claimed to. §8.1 makes this a rule; wire it into a fixture in Task 7.1.
5. Record calls with arguments, so a test can assert **that eligibility was called before schedule**
   — the ordering repo rule 3 depends on.
6. Unit tests for the mock: an unqueued call raises; a queued exception is raised; `assert_drained`
   fails with a leftover; the call log preserves order.
7. Reference: Low-Level Design §8.1; decision D21.

**Verification:**
- `cd server && uv run pytest tests/unit/carriers/test_scripted_adapter.py`

**Requirements covered:** NFR-6.3

---

### Track E: Server runtime mock carrier [server]

#### Task 4.14: `app/carriers/mock.py` — `MockCarrierAdapter`

**Prerequisites:** Task 3.5, Task 3.4
**Conflicts with:** None
**Parallel with:** Tasks 4.1–4.13
**Package:** `server/app/carriers`

**Objective:** Build the adapter a *running* deployment uses when `CARRIER_ADAPTER=mock` —
requirements §5.1's default until USPS credentials arrive (Task 0.2), and what Task 8.6's manual
acceptance run and every demo books against. Task 4.5's scripted double cannot do this job; it raises
on the first unscripted call by design. Decision D21.

**Instructions:**
1. Create `server/app/carriers/mock.py` with `MockCarrierAdapter` implementing `CarrierAdapter`. It
   lives at `carriers/`, not `carriers/usps/`, because it impersonates no specific carrier.
2. **Deterministic, not random.** Confirmation numbers are derived from the request, so the same
   booking twice yields the same number and a test can assert on it.
3. Every confirmation number carries a **fixed recognisable prefix** — the marker Task 8.5 renders as
   "simulated" (decision D22). Export the prefix as a module constant so the extension's expectation
   and the server's production of it are traceable to one definition; put it in `contracts/` (Task
   3.18) so both workspaces read the same value.
4. `check_eligibility` returns eligible for every address **except one designated unserviceable
   postcode**, declared as a module constant and documented in `server/AGENTS.md`.
   - **Why a deliberately failing postcode.** FR-3.4.2's graceful second answer — what the user sees
     when pickup is not available — is the hardest copy in the product to get right and the easiest
     to never see. An always-eligible mock means nobody looks at that path until a real user finds it.
5. `schedule` returns a next-available date computed from the current date, not a hard-coded one that
   silently goes stale.
6. `cancel` succeeds for a confirmation number this adapter issued and raises the documented
   not-found error otherwise.
7. Unit tests: the same request yields the same confirmation number; every issued number carries the
   prefix; the designated postcode is ineligible and every other tested one is eligible; cancelling
   an unknown number raises; the scheduled date is in the future relative to a frozen clock.
8. Wire it into `main.py`'s adapter selection in Task 6.5, keyed on `CARRIER_ADAPTER`.
9. Reference: requirements §5.1, FR-3.4.1, FR-3.4.2, FR-3.4.5, FR-3.4.6; decisions D21, D22.

**Verification:**
- `cd server && uv run pytest tests/unit/carriers/test_mock_adapter.py`
- With `CARRIER_ADAPTER=mock`, a schedule request against a running server returns a prefixed
  confirmation number rather than raising.

**Requirements covered:** §5.1, FR-3.4.1, FR-3.4.2

---

### Track C: Extension storage [extension]

#### Task 4.6: `src/storage/` — key layout, defensive read, and rebuild

**Prerequisites:** Task 2.4, Task 2.6
**Conflicts with:** Task 4.7 (both touch `src/storage/index.ts`)
**Parallel with:** Task 4.13, all server tasks
**Package:** `extension/src/storage`

**Objective:** Fix the key layout, make every read defensive, implement the rebuild whose
**pickup carve-out** is the part that must not be got wrong, and **write the barrel file once** so
the four repository tasks that follow do not serialise behind it.

**Instructions:**
1. Create `extension/src/storage/keys.ts` with the key scheme from §5.1 — one key per entity
   collection plus the singleton keys, all namespaced and versioned.
2. Create `extension/src/storage/read.ts` with `read_defensively(key, validate)`: a value that fails
   validation is treated as absent and the corruption is recorded; a read never throws into a caller.
3. Implement `rebuild()`: when the store's `schema_version` is behind, discard what cannot be
   migrated and rebuild — **except for pickups**. A booked pickup is a real-world commitment that
   exists at USPS whether or not this store remembers it, so `rebuild` preserves unsettled pickup
   records and their booked addresses. Add a `// dev-note:` with exactly that reasoning; a future
   reader simplifying `rebuild` to "clear everything" is the failure this note exists to stop.
4. **Write `extension/src/storage/index.ts` in this task, complete.** List every export the storage
   package will have — including the repositories Tasks 4.8–4.11 have not written yet — so those four
   tasks add a *file* each and never edit a shared one.
   - **Why this changed.** Tasks 4.6–4.12 were previously a seven-task fully serial chain, justified
     as protecting "one state machine, one serialising queue". The actual serialising constraint was
     this barrel file, not the invariant: each repository already lives in its own module. Writing
     the barrel up front drops Batch 4's long pole from 7 slots to about 4 — the largest single
     schedule improvement available in this plan. `StorageCoordinator.transact` stays whole in Task
     4.7, because *that* is a real invariant. Decision D19.
   - The barrel will reference modules that do not exist yet, so this task also adds the four empty
     module files with their type signatures and a `throw new Error("not implemented")` body. Tasks
     4.8–4.11 replace the bodies. Keep the placeholder throw, never a silent no-op return — an
     unimplemented repository must fail loudly if something wires it early.
5. Unit tests: a corrupt value reads as absent; a stale `schema_version` triggers rebuild; rebuild
   discards orders and returns but **keeps unsettled pickups and their booked addresses**; rebuild on
   a current version is a no-op; **importing `src/storage/index.ts` type-checks** with the
   placeholders in place.
6. Reference: Low-Level Design §5.1, §3.4; requirements FR-3.1.5, FR-3.4.5a, NFR-6.5; decision D19.

**Verification:**
- `cd extension && bun run test tests/storage/rebuild.test.ts`

**Requirements covered:** FR-3.1.5, NFR-6.5

---

#### Task 4.7: `StorageCoordinator.transact` — the serialising queue

**Prerequisites:** Task 4.6
**Conflicts with:** Task 4.6 (both touch `src/storage/index.ts`)
**Parallel with:** Task 4.13, all server tasks
**Package:** `extension/src/storage`

**Objective:** Implement the single write path: a queue that serialises mutations and commits each one
as **one** `chrome.storage.local.set`.

**Instructions:**
1. Create `extension/src/storage/coordinator.ts` with `transact(fn)`: queue the mutation, run it
   against a read snapshot, and commit the whole result in a single composed `set`.
2. Add a prominent `// dev-note:` restating §4.3: **this is a serialising queue, not a transaction.**
   `chrome.storage.local` is atomic per `set` and offers nothing across sets, so the guarantee here is
   "one composed write, one atomicity boundary" — not rollback. Naming it a transaction in a future
   refactor would invite exactly the assumption it cannot honour.
3. A rejected `set` (quota) surfaces to the caller with the store unchanged; the queue continues.
4. `transact` must not be re-entrant — a mutation that calls `transact` deadlocks. Detect and throw
   with a clear message rather than hanging.
5. Unit tests against the Task 2.6 fake: two concurrent `transact` calls apply in order and produce
   one `set` each; a multi-key mutation commits as a single `set` (assert the call count); an armed
   quota rejection leaves the store byte-identical; a re-entrant call throws.
6. Reference: Low-Level Design §4.3, §5.1.

**Verification:**
- `cd extension && bun run test tests/storage/coordinator.test.ts`

**Requirements covered:** FR-3.1.5

---

#### Task 4.8: `OrderRepository`

**Prerequisites:** Task 4.7
**Conflicts with:** None — `src/storage/orders.ts` only (the barrel was written in 4.6)
**Parallel with:** Tasks 4.9, 4.10, 4.11, 4.13, all server tasks
**Package:** `extension/src/storage`

**Objective:** Persist orders and their items, stamping `first_seen_at` from an injected clock.

**Instructions:**
1. Create `extension/src/storage/orders.ts` with `upsert`, `list`, `get`, `find_item`, `delete` — all
   mutations through `transact`.
2. `upsert` preserves an existing `first_seen_at` and sets it from the clock only on first insert.
   Re-scanning a page must not reset it; the ranking and the "new since last visit" reading both
   depend on it.
3. Unit tests: insert then re-upsert preserves `first_seen_at`; `find_item` locates an item across
   orders; `delete` removes the order and its items; `list` on an empty store returns empty, not
   undefined.
4. Reference: Low-Level Design §3.4, §5.1; requirements FR-3.1.5.

**Verification:**
- `cd extension && bun run test tests/storage/orders.test.ts`

**Requirements covered:** FR-3.1.5

---

#### Task 4.9: `ReturnRepository`

**Prerequisites:** Task 4.7
**Conflicts with:** None — `src/storage/returns.ts` only (the barrel was written in 4.6)
**Parallel with:** Tasks 4.8, 4.10, 4.11, 4.13, all server tasks
**Package:** `extension/src/storage`

**Objective:** Persist return requests and answer the one question the driver asks before starting:
is there already a live return for this item?

**Instructions:**
1. Create `extension/src/storage/returns.ts` with `create`, `update`, `active_for_item(item_id)`,
   `get`, `delete`.
2. `active_for_item` returns a return **only** if its state is one of the non-terminal FR-3.3.9
   states. The four terminals — `LabelPrinted`, `DroppedOff`, `HandedOff`, `Aborted` — are not
   active. This is the guard that makes "second return while one is live" refuse and "second return
   after an abort" succeed, and getting the terminal set wrong breaks exactly one of the two.
3. Unit tests: a `Driving` return is active; each of the four terminals is not active; `update`
   through a terminal makes it inactive; two items do not see each other's returns.
4. Reference: Low-Level Design §3.4, §5.1; requirements FR-3.3.9, FR-3.3.10.

**Verification:**
- `cd extension && bun run test tests/storage/returns.test.ts`

**Requirements covered:** FR-3.3.9, FR-3.3.10

---

#### Task 4.10: `PickupRepository`

**Prerequisites:** Task 4.7
**Conflicts with:** None — `src/storage/pickups.ts` only (the barrel was written in 4.6)
**Parallel with:** Tasks 4.8, 4.9, 4.11, 4.13, all server tasks
**Package:** `extension/src/storage`

**Objective:** Persist pickup intent and confirmation, deriving `Abandoned` and `Collected` at read
time rather than storing them.

**Instructions:**
1. Create `extension/src/storage/pickups.ts` with `save_intent`, `promote`, `get`,
   `list_unsettled`, `mark_collected`, `mark_abandoned`, `delete`.
2. **`save_intent` records the consent stamp and the address before the network call.** FR-3.4.5a
   requires the consent to survive a lost response, so it is written first; `promote` then attaches
   the `confirmation_number` and the day when the response arrives.
3. **No `etag` field, no setter for one** (rule 3). Add a `// dev-note:`.
4. `Abandoned` and `Collected` are **derived on read** from the stored day and settlement flags —
   §3.4 is explicit that they are not stored, so a store that sat idle past the pickup day reads
   correctly without a background job having written anything.
5. Unit tests: `save_intent` then a simulated lost response leaves a consented, unpromoted record;
   `promote` attaches the confirmation and day; a record whose day is in the past reads as
   `Abandoned` without any write; `mark_collected` settles it; `list_unsettled` excludes settled and
   abandoned records.
6. Reference: Low-Level Design §3.4, §5.1; requirements FR-3.4.3, FR-3.4.4, FR-3.4.5, FR-3.4.5a.

**Verification:**
- `cd extension && bun run test tests/storage/pickups.test.ts`

**Requirements covered:** FR-3.4.5, FR-3.4.5a, FR-3.4.6

---

#### Task 4.11: `AddressRepository` and `SessionStore`

**Prerequisites:** Task 4.7
**Conflicts with:** None — `src/storage/addresses.ts` and `session.ts` only (barrel written in 4.6)
**Parallel with:** Tasks 4.8, 4.9, 4.10, 4.13, all server tasks
**Package:** `extension/src/storage`

**Objective:** Two singleton-key stores: the user's pickup address, and the `DriverSession` the worker
rehydrates from.

**Instructions:**
1. Create `extension/src/storage/address.ts` with `get`, `set`, `clear` over one key.
2. Create `extension/src/storage/session.ts` with `get`, `set`, `clear` for `DriverSession`.
3. `SessionStore.get` returns the **full** session including `chosen_option` — §4.4's rehydration
   hands the driver back every field, and `chosen_option` in particular is read two transitions later
   by the carrier derivation.
4. Unit tests: address round-trips; a corrupt address reads as absent; the session round-trips with
   `chosen_option` set and with it null; `clear` on an absent session is a no-op.
5. Reference: Low-Level Design §3.5, §4.4, §5.1; requirements FR-3.3.5, FR-3.4.2.

**Verification:**
- `cd extension && bun run test tests/storage/session.test.ts tests/storage/address.test.ts`

**Requirements covered:** FR-3.3.5, FR-3.4.3, FR-3.4.8

---

#### Task 4.12: Coordinator cross-entity operations — eviction and clear-all

**Prerequisites:** Tasks 4.8, 4.9, 4.10, 4.11
**Conflicts with:** Task 4.7 (`src/storage/coordinator.ts`)
**Parallel with:** Task 4.13, all server tasks
**Package:** `extension/src/storage`

**Objective:** Keep the store under the cap without evicting anything the user is relying on, and
implement the clear-all that must not orphan a real-world commitment.

**Instructions:**
1. Add to `coordinator.ts`: `evict_if_over_cap()` and `evict_to_fit(incoming_bytes)`.
2. Measure with `chrome.storage.local.getBytesInUse` **before and after**, and evict down to
   `STORAGE_CAP_BYTES - STORAGE_EVICTION_MARGIN_BYTES` rather than to the cap. There is no
   `unlimitedStorage`, so a store that sits exactly at the cap fails the next write.
3. Build the **protected set** as the union of: items with an active return, unsettled pickups and
   their booked addresses, and the user's address. Eviction chooses among the rest — oldest
   `first_seen_at` first.
4. Eviction runs **inside** the caller's `transact`, never by calling `transact` again — Task 4.7
   makes re-entry throw, and this is the call site most likely to attempt it. `// dev-note:` it.
5. `clear_all()` removes everything, but must first surface any unsettled pickup so the caller can
   warn the user that a booked USPS pickup will still happen (the popup does the warning in Task
   8.5).
6. Unit tests: eviction leaves the store under cap-minus-margin; an item with an active return is
   never evicted; an unsettled pickup and its booked address are never evicted; eviction is measured
   with `getBytesInUse` not estimated; eviction inside a `transact` does not deadlock; `clear_all`
   reports the unsettled pickups it is about to drop.
7. Reference: Low-Level Design §4.3, §5.2; requirements FR-3.1.5, NFR-6.1, NFR-6.5.

**Verification:**
- `cd extension && bun run test tests/storage`

**Requirements covered:** FR-3.1.5, NFR-6.1, NFR-6.5

---

### Track D: Extension server client [extension]

#### Task 4.13: `src/api/` — the typed server client

**Prerequisites:** Task 3.15, Task 3.16, Task 2.5, Task 3.18
**Conflicts with:** None
**Parallel with:** Tasks 4.6–4.12, 4.14, all server tasks
**Package:** `extension/src/api`

**Objective:** Wrap the seven endpoints with typed calls, a reason-to-error map, and a retry policy
that knows which requests are safe to repeat.

**Instructions:**
1. Create `extension/src/api/client.ts` with one method per endpoint from requirements §4.1.
2. Every request carries **`X-Boomerang-Client-Version`** — the name is normative, from requirements
   §4.1 — with the value of `CLIENT_VERSION` from `src/config.ts`. A 4xx with reason `client-too-old`
   (requirements §4.2, floor set by `MIN_CLIENT_VERSION` in §5.1) maps to a distinct typed error the
   popup renders as "update required", never as a generic failure.
   - **Use the exact spelling Task 3.8's gate reads.** §4.2 makes an *absent* header a
     `client-too-old` rejection, so a mismatched spelling here rejects every request from the real
     client while both unit suites stay green. Task 3.18's golden payloads carry the header; assert
     against them rather than against a string typed twice. Decision D16.
3. Map each of the nine documented kebab-case `reason` codes to a typed error, and surface
   `message` and `request_id` — the popup's failure copy quotes the id as "reference: <id>" per §4.2.
   `details.servable_locations` on `location-not-serviceable` is the one payload a caller reads.
   An **unrecognised** reason maps to a generic
   upstream error rather than being dropped — the client must not assume it knows every reason the
   server can produce.
4. Retry policy: bounded retry with backoff for read-only calls; **no retry for `POST /pickups` or
   `DELETE /pickups/{id}`.** A retried schedule can double-book a real USPS pickup and a retried
   cancel can race a refresh. `// dev-note:` this — it is the kind of rule a later "just add retries
   everywhere" change would erase.
5. Responses go through Task 3.16's validators before returning.
6. Timeouts from **`API_REQUEST_TIMEOUT_MS`** — the per-attempt ceiling — and the retry loop from
   step 4 bounded by **`API_RETRY_BUDGET_MS`**, the total wall-clock budget across attempts. A
   timeout is a typed error, not a hang.
   - Both names are normative (requirements §5.1). This task previously said `API_TIMEOUT_MS`, which
     exists in no document, and never mentioned the retry budget at all — so the bound on step 4's
     "bounded retry" would have been invented locally. Decision D17.
7. Unit tests with a fetch double: each endpoint issues the documented method and path; **the header
   is spelled `X-Boomerang-Client-Version`** on all seven; each documented reason maps to its error;
   an unknown reason maps to the generic one; a 503 on a GET retries within the bound; a 503 on
   `POST /pickups` does **not** retry; **retries stop once `API_RETRY_BUDGET_MS` is exhausted even if
   the attempt count allows more**; a timeout raises the timeout error; an invalid response body
   rejects; every request and response shape matches its `contracts/` fixture.
8. Reference: Low-Level Design §3.4, §6.1; requirements §4.1, §4.2, §5.1, NFR-6.3; decisions D16, D17.

**Verification:**
- `cd extension && bun run test tests/api`

**Requirements covered:** §4.1, §4.2, NFR-6.3

---

### Batch 4 Commit Checkpoint

After all tracks complete:
- [ ] Server tests pass: `cd server && uv run pytest`
- [ ] Extension tests pass: `cd extension && bunx tsc --noEmit && bun run test`
- [ ] The server can talk to Bedrock with forced tool choice and to USPS with a cached token, and has
      a scriptable carrier double for integration tests.
- [ ] The extension has its whole persistence layer, including eviction that protects live returns and
      unsettled pickups, and a server client that refuses to retry a booking.

---

## Batch 5: Services and Driver Collaborators

### Track A: Server ingest service [server]

#### Task 5.1: `app/services/ingest.py` — `IngestService`

**Prerequisites:** Task 4.1, Task 4.2, Task 3.2, Task 3.7, Task 2.1
**Conflicts with:** None
**Parallel with:** Tasks 5.2–5.6
**Package:** `server/app/services`

**Objective:** Turn an extracted page into parsed orders with derived return windows, or into a
typed failure.

**Instructions:**
1. Create `server/app/services/ingest.py` with `IngestService.ingest(request, now)`.
2. Call the model through `bedrock.invoke_with_tool("parse", ...)` with the Task 4.1 parse tool.
3. Run `derive_window` (Task 3.7) over each parsed item and attach the deadline and its basis.
4. A model result that yields no usable order raises `ParseUnusable` — the endpoint reports it rather
   than returning an empty list, because "we could not read this page" and "this page has no orders"
   are different answers to the user.
5. **No `fastapi` import.** §2.1 forbids it; the service raises, the route translates.
6. Unit tests with a mocked Bedrock transport: a good page yields orders with windows; an empty tool
   result raises `ParseUnusable`; a transport failure raises `ModelUnavailable`; the derived window
   matches Task 3.7 for a fixed `now`.
7. Reference: Low-Level Design §3.3, §4.1; requirements FR-3.2.1, FR-3.2.2, FR-3.1.4.

**Verification:**
- `cd server && uv run pytest tests/unit/services/test_ingest.py`

**Requirements covered:** FR-3.1.4, FR-3.2.1, NFR-6.4

---

### Track B: Server action service [server]

#### Task 5.2: `app/services/action.py` — `ActionService`

**Prerequisites:** Task 4.1, Task 4.2, Task 3.3, Task 2.1
**Conflicts with:** None
**Parallel with:** Tasks 5.1, 5.3–5.6
**Package:** `server/app/services`

**Objective:** Ask the model for the next action under forced tool choice and return it as a
validated `ProposedAction`.

**Instructions:**
1. Create `server/app/services/action.py` with `ActionService.next_step(request)`.
2. Force the action tool. The model has **no** free-text path — a completion without a tool use is
   `ParseUnusable`, not something to parse.
3. Validate the tool input into `ProposedAction` (Task 3.3) before returning. The server validates
   even though the extension validates again: two sides of a trust boundary each check, and the
   extension's check is the one that binds `fill` to the adapter's allowlist, which the server cannot
   know.
4. Pass the fillable-field descriptors through to the prompt so the model proposes targets that can
   be honoured, while remembering the extension enforces the bound.
5. Unit tests: a forced tool call returns a `ProposedAction`; a text-only completion raises
   `ParseUnusable`; a tool input with an invented kind raises validation; each of the five kinds
   round-trips; a transport failure raises `ModelUnavailable`.
6. Reference: Low-Level Design §3.3, §4.2; requirements FR-3.3.7, FR-3.3.8; repo `AGENTS.md` rule 9.

**Verification:**
- `cd server && uv run pytest tests/unit/services/test_action.py`

**Requirements covered:** FR-3.3.7, FR-3.3.8

---

### Track C: Server pickup service [server]

#### Task 5.3: `app/services/pickup.py` — `PickupService`

**Prerequisites:** Task 3.5, Task 3.4, Task 2.1
**Conflicts with:** None
**Parallel with:** Tasks 5.1, 5.2, 5.4–5.6
**Package:** `server/app/services`

**Objective:** Own the pickup rules that must hold regardless of which carrier adapter is behind
them — the eligibility gate, the postage gate, and refresh-then-cancel.

**Instructions:**
1. Create `server/app/services/pickup.py` with `check_eligibility`, `schedule`, `refresh`, `cancel`.
2. **`schedule` refuses unless an eligibility check for that address succeeded** (rule 3). The gate
   lives here, not in the route, so no future caller can bypass it. Raise `PickupIneligible`
   otherwise.
3. **`schedule` also refuses unless the postage carrier on the box is USPS** (rule 4). A printed UPS
   or FedEx label is a valid return and an invalid pickup; the refusal names that, so the caller can
   say why rather than reporting a generic failure.
4. `cancel` performs a **refresh first** to obtain a current ETag, then cancels with it. If the
   refresh reports the pickup already collected, cancel returns that outcome rather than attempting
   the cancel (rule 3).
5. The ETag never leaves this function — it is not returned, not logged, not persisted.
6. Unit tests against `ScriptedUspsAdapter` (Task 4.5): schedule without a prior eligibility check raises; schedule
   with a non-USPS postage carrier raises; schedule after a successful check succeeds and the mock's
   call log shows eligibility first; cancel calls refresh then cancel in that order; cancel on an
   already-collected pickup returns collected without calling cancel; a refresh failure surfaces as
   `CarrierUnavailable` and no cancel is attempted.
7. Reference: Low-Level Design §3.3, §4.3, §4.5; requirements FR-3.4.1–FR-3.4.8; repo `AGENTS.md`
   rules 3, 4.

**Verification:**
- `cd server && uv run pytest tests/unit/services/test_pickup.py`

**Requirements covered:** FR-3.4.1, FR-3.4.3, FR-3.4.4, FR-3.4.5, FR-3.4.6, FR-3.4.8

---

### Track D: Extension driver collaborators [extension]

#### Task 5.4: `TabHandle`, `TabHandleFactory`, and `UserPrompt`

**Prerequisites:** Task 2.4, Task 2.7
**Conflicts with:** Task 5.5 (both export from `src/driver/index.ts`)
**Parallel with:** Tasks 5.1–5.3, 5.6
**Package:** `extension/src/driver`

**Objective:** Give the driver a tab abstraction it can hold across a worker death, and a prompt
abstraction that turns a user question into a persisted pause rather than a blocking wait.

**Instructions:**
1. Create `extension/src/driver/tab.ts` with `TabHandle` exposing `url`, `dom()`, `is_live()`,
   `navigate()`, and `TabHandleFactory.from_session(session)` / `create(url)`.
2. `is_live()` asks `chrome.tabs.get` — the handle holds a tab **id**, not a tab object, because the
   worker that created it may be gone. A stale handle reports not live rather than throwing.
3. Create `extension/src/driver/prompt.ts` with `UserPrompt`: asking the user records the question in
   the session and **returns**; it does not await. The answer arrives later as a message (Task 5.6),
   possibly to a different worker instance.
4. `// dev-note:` on `UserPrompt`: an `await` here would be a promise the worker cannot keep — it dies
   after ~30s idle and the user takes longer than that.
5. Unit tests: a handle for a closed tab reports not live; `dom()` on a closed tab fails cleanly;
   asking a question persists it and returns immediately; a handle rebuilt from a session reaches the
   same tab.
6. Reference: Low-Level Design §3.4, §4.4; requirements FR-3.3.7, FR-3.3.8.

**Verification:**
- `cd extension && bun run test tests/driver/tab.test.ts tests/driver/prompt.test.ts`

**Requirements covered:** FR-3.3.3, FR-3.3.9

---

#### Task 5.5: `StepExecutor`

**Prerequisites:** Task 5.4, Task 3.15
**Conflicts with:** Task 5.4 (`src/driver/index.ts`)
**Parallel with:** Tasks 5.1–5.3, 5.6
**Package:** `extension/src/driver`

**Objective:** Execute a `ValidatedAction` against a tab — and accept nothing else.

**Instructions:**
1. Create `extension/src/driver/executor.ts` with `execute(action: ValidatedAction, tab: TabHandle)`.
2. The parameter type is `ValidatedAction`, never `ProposedAction`. Since only Task 3.15 can construct
   one, "did this action get validated?" is settled by the compiler.
3. Implement `click`, `select_option`, `fill` via `chrome.scripting`. `pause_for_user` and
   `report_stuck` are **not executed here** — they are outcomes the driver acts on. Return them as
   results rather than performing anything.
4. An execution whose selector no longer resolves returns a miss, not a throw — the driver decides
   whether that means fallback or failure.
5. Unit tests: each executable kind produces the expected scripting call; a `fill` writes the value; a
   vanished selector returns a miss; `pause_for_user` performs no scripting call; passing an
   unvalidated object is a type error (type-level test).
6. Reference: Low-Level Design §3.4, §4.2; requirements FR-3.3.3, FR-3.3.8.

**Verification:**
- `cd extension && bun run test tests/driver/executor.test.ts`

**Requirements covered:** FR-3.3.3, FR-3.3.8

---

### Track E: Extension messaging [extension]

#### Task 5.6: `src/messaging/` — internal message routing

**Prerequisites:** Task 4.12, Task 2.4
**Conflicts with:** None
**Parallel with:** Tasks 5.1–5.5
**Package:** `extension/src/messaging`

**Objective:** Define the enumerated message set and route it between the popup, the content script
and the worker.

**The external half of this task was removed.** FR-3.6.3 — the dashboard messaging the extension over
`externally_connectable` — is cut from PoC scope, because the dashboard origin it depends on does not
exist and high-level design §11 Q1 records the hostname as undecided. There is no `on_external`
handler, no `DASHBOARD_ORIGIN`, and no external message subset. Decision D6.

**Instructions:**
1. Create `extension/src/messaging/messages.ts` with a discriminated union covering every message the
   popup and content script can send. An unknown type is rejected, not forwarded.
2. Create `extension/src/messaging/router.ts` with an `on_internal` handler.
3. Add a `// dev-note:` recording the D6 cut and what reinstating it would require: an
   `externally_connectable` manifest key naming a real dashboard origin, an `on_external` handler that
   verifies `sender.origin` **before** dispatch, and a strict read-only subset of the message set —
   the dashboard would read, never drive a return. Note also that `externally_connectable` is a
   filter, not an authorisation check. Writing this down now is cheaper than rediscovering it.
4. Unit tests: a valid internal message dispatches; an unknown type is rejected; a message arriving
   from outside the extension is rejected without dispatch.
5. Reference: Low-Level Design §3.4, §7.2; requirements FR-3.6.1, NFR-6.5; decision D6.

**Verification:**
- `cd extension && bun run test tests/messaging`

**Requirements covered:** FR-3.6.1, NFR-6.5

---

### Batch 5 Commit Checkpoint

After all tracks complete:
- [ ] Server tests pass: `cd server && uv run pytest`
- [ ] Extension tests pass: `cd extension && bunx tsc --noEmit && bun run test`
- [ ] All server business logic exists and is unit-tested, including both gates on scheduling.
- [ ] The extension's driver collaborators exist and messaging checks the dashboard's origin.

---

## Batch 6: Routes and Application; Driver Core

### Track A: Server routes and application [server]

#### Task 6.1: `app/routes/health.py`

**Prerequisites:** Task 1.1
**Conflicts with:** Tasks 6.2–6.4 (`app/routes/__init__.py`)
**Parallel with:** Tasks 6.6–6.8 (extension)
**Package:** `server/app/routes`

**Objective:** Move the existing inline `/health` handler into the routes package unchanged in
behaviour.

**Instructions:**
1. Create `server/app/routes/__init__.py` and `server/app/routes/health.py` with an `APIRouter`
   exposing `GET /health` returning `{"status": "ok"}`.
2. `/health` performs **no** upstream call and requires **no** client version — a health check that
   depends on Bedrock or USPS reports their health, not ours, and a version-gated health check is
   unusable from a load balancer.
3. Unit test: the route returns 200 and the documented body.
4. Reference: Low-Level Design §3.3, §7.1.

**Verification:**
- `cd server && uv run pytest tests/unit/routes/test_health.py`

**Requirements covered:** NFR-6.3, NFR-6.7

---

#### Task 6.2: `app/routes/orders.py` — `POST /orders/ingest`

**Prerequisites:** Task 5.1, Task 3.8, Task 6.1
**Conflicts with:** Tasks 6.1, 6.3, 6.4 (`app/routes/__init__.py`)
**Parallel with:** Tasks 6.6–6.8
**Package:** `server/app/routes`

**Objective:** Expose ingestion, gated on client version, translating service errors to the documented
response shape.

**Instructions:**
1. Create `server/app/routes/orders.py` with `POST /orders/ingest`, depending on
   `require_supported_client` and on `IngestService`.
2. The route calls the service and nothing else — no Bedrock, no carrier (§2.1).
3. Errors propagate as `BoomerangError`; `main.py`'s handler renders them (Task 6.5). The route
   contains no `try`/`except` for reason mapping.
4. Unit tests with a stub service: a good request returns the documented body; a version below the
   floor returns the version reason **and the service is never called**; a payload over the ceiling
   returns `payload-too-large` from model validation.
5. Reference: Low-Level Design §3.3, §4.1; requirements §4.1, §5.1, FR-3.1.3, FR-3.1.4.

**Verification:**
- `cd server && uv run pytest tests/unit/routes/test_orders.py`

**Requirements covered:** §4.1, FR-3.1.3, FR-3.1.4, FR-3.2.1

---

#### Task 6.3: `app/routes/returns.py` — `POST /returns/next-step`

**Prerequisites:** Task 5.2, Task 3.8, Task 6.2
**Conflicts with:** Tasks 6.1, 6.2, 6.4 (`app/routes/__init__.py`)
**Parallel with:** Tasks 6.6–6.8
**Package:** `server/app/routes`

**Objective:** Expose the next-action endpoint, gated on client version.

**Instructions:**
1. Create `server/app/routes/returns.py` with `POST /returns/next-step` depending on
   `require_supported_client` and `ActionService`.
2. Unit tests with a stub service: a good request returns a `ProposedAction` body; `upstream-unavailable`
   renders with the documented reason and status; a version below the floor returns the version reason
   and the service is never called.
3. Reference: Low-Level Design §3.3, §4.2; requirements §4.1, §5.1, FR-3.3.8.

**Verification:**
- `cd server && uv run pytest tests/unit/routes/test_returns.py`

**Requirements covered:** §4.1, FR-3.3.8

---

#### Task 6.4: `app/routes/pickups.py` — the four pickup endpoints

**Prerequisites:** Task 5.3, Task 3.8, Task 6.3
**Conflicts with:** Tasks 6.1–6.3 (`app/routes/__init__.py`)
**Parallel with:** Tasks 6.6–6.8
**Package:** `server/app/routes`

**Objective:** Expose eligibility, schedule, refresh and cancel over `PickupService`.

**Instructions:**
1. Create `server/app/routes/pickups.py` with the four endpoints from requirements §4.1, each
   depending on `require_supported_client`, `PickupService`, and `get_carrier_adapter`.
2. A **not-serviceable** eligibility result is a normal 200 body carrying the carrier's reason, not an
   error status. An **ineligible schedule attempt** is the error. The distinction is the difference
   between "USPS says no here" and "you asked us to book without checking."
3. No route reads or writes an ETag; `cancel` simply calls the service.
4. Unit tests with a stub service: each endpoint's method and path match §4.1; not-serviceable returns
   200 with the reason; ineligible schedule returns the documented error; already-collected cancel
   returns the collected outcome.
5. Reference: Low-Level Design §3.3, §4.3, §4.5; requirements §4.1, FR-3.4.1–FR-3.4.7.

**Verification:**
- `cd server && uv run pytest tests/unit/routes/test_pickups.py`

**Requirements covered:** §4.1, FR-3.4.1, FR-3.4.6, FR-3.4.8

---

#### Task 6.5: `app/main.py` — lifespan, handlers, CORS, Mangum

**Prerequisites:** Tasks 6.1, 6.2, 6.3, 6.4, 3.6, 4.4, 4.14, 4.2, 2.2
**Conflicts with:** None
**Parallel with:** Tasks 6.6–6.8
**Package:** `server/app`

**Objective:** Wire the application in the order §7.1 specifies, and render every `BoomerangError`
into the one documented body shape.

**Instructions:**
1. Modify `server/app/main.py`, preserving the existing `lifespan` + `verify_config()` shape and
   extending it to the full §7.1 startup order: load and validate `Settings` → configure logging →
   verify Bedrock config → construct the carrier adapter → attach both to `app.state` → register
   middleware and routers.
2. **Fail fast:** any step raising aborts startup. A container that boots with a missing USPS
   credential and discovers it on the first user request has turned a deploy-time error into a
   user-facing one.
3. Register an exception handler for `BoomerangError` rendering `ErrorBody` with the class's status,
   and a `RequestValidationError` handler rendering the same shape (a 422 must not leak pydantic's
   internal structure to the extension, which maps on `reason`).
4. Configure CORS from `Settings.allowed_origins` — an explicit list, never `*`.
5. Register `RequestIdMiddleware`.
6. Export `handler = Mangum(app)` for Lambda.
7. **Select the adapter on `CARRIER_ADAPTER` (requirements §5.1):** `usps` constructs `UspsAdapter`
   (Task 4.4); `mock` constructs `MockCarrierAdapter` (Task 4.14). Any other value **fails startup** —
   an unrecognised adapter name must not silently fall back to either one. Integration tests
   substitute `ScriptedUspsAdapter` (Task 4.5) at this same seam (Task 7.1), which is why the adapter
   is constructed here and injected rather than imported by services.
   - `ScriptedUspsAdapter` is a test double and **must not be reachable from `CARRIER_ADAPTER`**. Add
     a unit test asserting that no configuration value selects it (decision D21).
8. **Log the selected adapter at startup, at warning level when it is `mock`.** Requirements §5.1
   names the failure this guards: a deployment that silently runs on the mock returns fabricated
   confirmation numbers. The operator-facing half of that guard is this line; the user-facing half is
   the simulated-booking label in Task 8.5 (decision D22).
9. Unit tests: startup fails when a required setting is missing; startup fails on an unknown
   `CARRIER_ADAPTER`; `mock` selects `MockCarrierAdapter` and logs a warning; a `BoomerangError`
   renders the documented body and status; a validation error renders the same shape; the CORS header
   reflects a configured origin and is absent for an unconfigured one; `/health` responds.
10. Reference: Low-Level Design §7.1, §6.1, §6.2; requirements §5.1, NFR-6.4, NFR-6.6; decisions D21,
    D22.

**Verification:**
- `cd server && uv run pytest tests/unit` and `cd server && uv run fastapi dev app/main.py` starts.

**Requirements covered:** §4.2, NFR-6.5, NFR-6.6, NFR-6.7

---

### Track B: Extension driver core [extension]

#### Task 6.6: `ReturnDriver` — construction, `transition`, and `start`

**Prerequisites:** Task 4.9, Task 4.11, Task 5.4, Task 5.5
**Conflicts with:** Tasks 6.7, 6.8 (all in `src/driver/driver.ts`)
**Parallel with:** Tasks 6.1–6.5 (server)
**Package:** `extension/src/driver`

**Objective:** Establish the driver's spine: the persist-before-act transition, and a `start` that
refuses to open a second live return for the same item.

**Instructions:**
1. Create `extension/src/driver/driver.ts` with `ReturnDriver`, taking its collaborators by
   constructor injection (repositories, `SessionStore`, API client, executor, tab factory, prompt,
   adapter registry, clock).
2. Implement `transition(next_state, patch)`: write the `DriverSession` **and** the `ReturnRequest`
   in **one** `transact`, then act. Never act then persist. `// dev-note:` §1.1 constraint 1: the
   worker dies mid-flow routinely, so the only state that exists is the state that was written.
3. Implement `start(item_id)`: check `ReturnRepository.active_for_item` first. A live return means
   refuse and surface the existing one; a terminal one means a new return may begin.
4. `attempt_count` increments on each step attempt and `RETURN_ATTEMPT_LIMIT` bounds it; exceeding it
   transitions to `Stalled`, not to a retry loop.
5. Unit tests: `transition` issues exactly one `set` for session plus return; a failure in the write
   leaves the prior state intact and does not act; `start` on an item with a `Driving` return refuses;
   `start` after an `Aborted` return succeeds; the attempt limit produces `Stalled`.
6. Reference: Low-Level Design §3.4, §4.3, §4.4; requirements FR-3.3.9, FR-3.3.10.

**Verification:**
- `cd extension && bun run test tests/driver/driver.test.ts`

**Requirements covered:** FR-3.3.1, FR-3.3.9, FR-3.3.10

---

#### Task 6.7: State machine edges and rehydration

**Prerequisites:** Task 6.6
**Conflicts with:** Tasks 6.6, 6.8 (`src/driver/driver.ts`)
**Parallel with:** Tasks 6.1–6.5
**Package:** `extension/src/driver`

**Objective:** Implement the FR-3.3.9 machine as a table of permitted edges, and the §4.4 rehydration
that lets a fresh worker resume from storage alone.

**Instructions:**
1. Add an explicit edge table: every permitted `(from, to)` pair. A transition not in the table throws
   rather than being taken — an illegal edge is a bug to surface, not a state to enter.
2. Implement `resume()`: read the session from `SessionStore`, rebuild the `TabHandle` from
   `tab_id`/`tab_url`, and continue from `state` and `step_key`. **Rehydration returns every field,
   `chosen_option` included** (§4.4) — it is read two transitions later by Task 7.8's derivation.
3. If the tab is no longer live, transition to `HandedOff` — the user's browser moved on and the
   flow cannot silently drive a tab that is gone.
4. If the session's state is terminal, `resume()` is a no-op.
5. Unit tests, with the Task 2.7 worker double: killing the worker at `Driving` and resuming lands on
   the same `step_key`; killing at `AwaitingConfirm` resumes awaiting; resuming with a closed tab
   yields `HandedOff`; resuming a terminal session does nothing; an illegal edge throws; **resume
   returns a session whose `chosen_option` is the value written before the death**.
6. Reference: Low-Level Design §3.5, §4.4; requirements FR-3.3.9, FR-3.3.5.

**Verification:**
- `cd extension && bun run test tests/driver/resume.test.ts`

**Requirements covered:** FR-3.3.5, FR-3.3.9, NFR-6.3

---

#### Task 6.8: Selector-first step loop and the model fallback

**Prerequisites:** Task 6.7, Task 3.10, Task 4.13, Task 5.5
**Conflicts with:** Tasks 6.6, 6.7 (`src/driver/driver.ts`)
**Parallel with:** Tasks 6.1–6.5
**Package:** `extension/src/driver`

**Objective:** Implement §4.2 — try the adapter's selectors first, ask the model only when they miss,
and refuse to send a payload the egress scan flagged.

**Instructions:**
1. Implement `step()`: resolve the adapter's selector for `step_key`; on a hit, build the action,
   validate it, execute it, and transition. The model is **not** consulted on the happy path.
2. On a selector miss, take the fallback: extract the step's DOM, run `scan_for_pii` (Task 3.10),
   and:
   - **flagged → do not send.** Transition to `Stalled` with a `report_stuck` outcome. The scan is
     fail-closed, so a scan that threw arrives here as flagged and takes the same branch. `// dev-note:`
     that this module owns the consequence and `src/extract/` owns only the check.
   - clean → call `POST /returns/next-step` under `MODEL_FALLBACK_TIMEOUT_MS`.
3. Validate the returned `ProposedAction` (Task 3.15). A rejection is **not** retried with the model —
   it transitions to `Stalled` via `report_stuck`. A model that proposed something outside the
   vocabulary does not get a second try at it.
4. `pause_for_user` transitions to `AwaitingConfirm` and asks through `UserPrompt`; `report_stuck`
   transitions to `Stalled`.
5. **Confirm before executing** any action the design marks as requiring confirmation, per FR-3.3.7 —
   the confirmation is a persisted transition, not an in-memory flag.
6. A fallback timeout transitions to `Stalled` rather than hanging.
7. Unit tests: a selector hit performs no API call; a miss with a clean payload calls the endpoint
   once; a miss with a flagged payload calls the endpoint **zero** times and lands `Stalled`; a
   scan that throws behaves identically to a flag; a validation rejection lands `Stalled` without a
   second model call; a timeout lands `Stalled`; `pause_for_user` lands `AwaitingConfirm`.
8. Reference: Low-Level Design §4.2, §6.1; requirements FR-3.1.3, FR-3.3.3, FR-3.3.7, FR-3.3.8.

**Verification:**
- `cd extension && bun run test tests/driver/step.test.ts`

**Requirements covered:** FR-3.1.3, FR-3.3.3, FR-3.3.7, FR-3.3.8, NFR-6.4

---

### Batch 6 Commit Checkpoint

After all tracks complete:
- [ ] Server tests pass and the app starts: `cd server && uv run pytest && uv run fastapi dev app/main.py`
- [ ] Extension tests pass: `cd extension && bunx tsc --noEmit && bun run test`
- [ ] All seven endpoints are served, version-gated, and render one error shape.
- [ ] The driver drives a return with selectors, falls back to the model only when it must, and
      survives a worker death by rehydrating from storage.

---

## Deployment Track

**Not a batch.** This track has no barrier and blocks nothing downstream. It opens the moment Task
6.5 exports the Mangum handler — the last thing infra actually needs — and runs in parallel with
Batches 7 through 10. Running it as a trailing batch would idle it through four batches for no
dependency reason and push the first real deployment to the end of the project, which is exactly
where deployment surprises are most expensive. Decisions D7–D9, D12.

**Its specification already exists.** [`infra/AGENTS.md`](../infra/AGENTS.md) was rewritten for this
architecture and carries the resource table, the sizing, the two-environment split, and the
reasoning behind every choice most likely to be "helpfully" reversed. These tasks implement it; they
do not re-decide it. Read it before opening an editor.

---

### Task I.1: Replace the Terraform with the Lambda topology

**Prerequisites:** Task 6.5 (a deployable handler), Task 1.4 (the pinned extension IDs)
**Conflicts with:** None
**Parallel with:** All of Batches 7–10
**Package:** `infra/`

**Objective:** Zero of this plan's original 79 tasks touched `infra/`, while NFR-6.6 and NFR-6.7 had
traceability rows pointing at application tasks that cannot satisfy them — no application task can
create a CloudWatch alarm. Close that.

**Instructions:**
1. **Delete** the VPC, internet gateway, subnets, EC2 instance and security group from
   `infra/main.tf`, along with the `vpc_cidr`, `instance_type` and `allowed_cidr` variables and any
   output that referenced them. `infra/AGENTS.md` explicitly instructs this deletion; do not leave
   the old resources beside the new ones "in case".
2. Provision, per the resource table in `infra/AGENTS.md`:
   - the **Lambda function** — 1024 MB, 60 s timeout, ARM, and
     `reserved_concurrent_executions = 5`;
   - the **Function URL** with auth type `NONE` and CORS restricted to **exactly one**
     `chrome-extension://` origin — the extension ID Task 1.4 derived for this environment;
   - the **IAM execution role**: Bedrock invoke, Parameter Store read, KMS decrypt, log write, least
     privilege and path-scoped, and **without** read access to
     `/boomerang/release/<env>/extension-key`;
   - **SSM `SecureString`** parameters for the USPS client ID and secret — Terraform grants access
     and never holds the value, because state is plaintext and retained;
   - the **CloudWatch log group** with **30-day retention set explicitly** — an unset log group
     retains forever;
   - **Bedrock model invocation logging explicitly disabled**, asserted off rather than left
     unconfigured. With it on, Bedrock writes full request bodies to S3 or CloudWatch, and the
     request body on the ingest path is the user's order-page DOM — that one setting falsifies
     NFR-6.1 without any application code changing;
   - **alarms** on Lambda error rate, Lambda `Throttles`, USPS failure rate and Bedrock
     `InputTokenCount`, plus an **AWS Budget** at $20/day.
3. Two environments, `dev` and `prod`, sharing nothing: separate Function URLs, log groups, CORS
   origins and SSM paths, with the execution role scoped so `dev` cannot read `prod`.
4. **Delete the "Legacy scaffold" section of `infra/AGENTS.md`** in this same change — the section
   ends with the instruction to do so once these resources land. Leaving it turns an accurate
   document into a misleading one the moment this task completes.
5. Keep `terraform.tfvars.example` in sync with every variable added or removed.
6. Reference: high-level design §6.1, §6.2, §8.2, §8.3, §8.4; `infra/AGENTS.md`; requirements
   NFR-6.5, NFR-6.6, NFR-6.7; decisions D7, D8.

**Verification:**
- `cd infra && terraform init && terraform validate && terraform plan` — plans cleanly with no VPC,
  EC2 or security-group resource in the plan output.
- `grep -ri "aws_vpc\|aws_instance\|aws_security_group" infra/` returns nothing.
- The planned Function URL CORS block names exactly one origin, and it matches the extension ID in
  `extension/AGENTS.md`.
- `terraform plan` shows Bedrock invocation logging disabled and log-group retention set to 30 days.

**Requirements covered:** NFR-6.5, NFR-6.6, NFR-6.7

---

### Task I.2: First deploy and a live smoke test

**Prerequisites:** Task I.1
**Conflicts with:** None
**Parallel with:** All of Batches 7–10
**Package:** `infra/`

**Objective:** Prove the deployed thing serves the same seven endpoints the test suite serves, from
a real browser origin, before Batch 10 starts asserting things about a bundle nobody has run against
a real server.

**Instructions:**
1. Apply to `dev`. State is local today — `infra/AGENTS.md` warns that a second person applying will
   corrupt it, so either move to the S3 backend it sketches or make it explicit that exactly one
   person applies during the PoC.
2. Write the USPS credentials into SSM by hand. If Task 0.2's access has not arrived, deploy with
   `CARRIER_ADAPTER=mock` and confirm the startup log emits the Task 6.5 warning.
3. Smoke test from a real loaded extension, not `curl`: `/health` responds; one ingest round trip
   succeeds; and a request from **any other origin is rejected by CORS**. The last one is the
   assertion that matters — it is the only browser-side control on an unauthenticated endpoint.
4. Record the deployed Function URL and the measured cold-start time in `docs/spikes/deploy.md`.
   Compare the cold start against NFR-6.4's budget and against Task 0.3's measurement; a cold start
   that breaks the budget is an upstream amendment (decision D25), not a footnote.

**Verification:**
- `/health` returns 200 over the Function URL.
- A request with a spoofed `Origin` header is refused.
- `docs/spikes/deploy.md` records the URL and the cold-start figure.

**Requirements covered:** NFR-6.4, NFR-6.5

---

### Task I.3: Reconcile `UspsAdapter` against the USPS sandbox

**Prerequisites:** Task I.1, Task 0.2 (credentials granted), Task 4.4
**Conflicts with:** None
**Parallel with:** All of Batches 7–10
**Package:** `server/app/carriers/usps`

**Objective:** Tasks 4.3–4.5 build the USPS client against `respx` mocks written from documentation.
Nobody has seen a real USPS response. This task is where "built against the documented contract"
becomes "verified the contract is real". High-level design §11 Q11 — what USPS does on a duplicate
booking — has no answer, and this is the task that answers it. Decision D12.

**If credentials have not arrived, this task does not run.** It is on no critical path, blocks
nothing, and its absence is a known risk rather than a schedule failure. Say so in the status
tracker rather than quietly marking it done.

**Instructions:**
1. Against the USPS sandbox, exercise each method `UspsAdapter` implements: token acquisition,
   eligibility, schedule, refresh, cancel.
2. **Diff every real response against the `respx` fixture** that stands in for it. Field names,
   nesting, date formats, and error bodies are the four places documentation and reality routinely
   diverge.
3. Update the fixtures to the observed shapes and re-run the Batch 4 and Batch 7 suites. A fixture
   change that breaks a test is this task finding a real defect; fix the adapter, not the assertion.
4. **Answer HLD §11 Q11 empirically:** book a pickup, then book an identical one. Record what USPS
   does — a second confirmation, an error, a silent no-op — in `docs/spikes/usps-sandbox.md`, and
   raise it as an upstream amendment if FR-3.4.5's behaviour depends on an answer the design
   assumed differently.
5. Record token TTL and any rate limit observed; both are inputs the token provider guessed at.

**Verification:**
- `docs/spikes/usps-sandbox.md` records one observed response per method plus the duplicate-booking
  answer.
- `cd server && make check` passes with the reconciled fixtures.

**Requirements covered:** FR-3.4.1, FR-3.4.5, FR-3.4.6, FR-3.4.8

---

## Batch 7: Server Integration Tests; Driver Flows

### Track A: Server integration harness [server]

#### Task 7.1: Integration test harness

**Prerequisites:** Task 6.5, Task 4.5
**Conflicts with:** None
**Parallel with:** Tasks 7.7–7.10 (extension)
**Package:** `server/tests/integration`

**Objective:** Build the fixture that constructs the real ASGI app with a scripted carrier and a
mocked Bedrock transport, so every §8.3 server row exercises the wired graph rather than a stub.

**Instructions:**
1. Add to `server/tests/conftest.py`: an `app` fixture running the real lifespan against a test
   `Settings`, substituting `ScriptedUspsAdapter` on `app.state`, and an `httpx.AsyncClient` bound to it
   with `ASGITransport`.
2. Add a Bedrock transport fixture supplying recorded tool-use responses per call site, so a test
   states what the model returned without ever reaching AWS.
3. Add an autouse teardown calling `ScriptedUspsAdapter.assert_drained()` — a queued outcome no call
   consumed fails the test (§8.1).
4. Add a `caplog`-based helper asserting that no log record contains a given substring, for the
   redaction rows.
5. Verify the harness with one smoke test: `GET /health` through the real app returns 200.
6. Reference: Low-Level Design §8.1, §8.3.

**Verification:**
- `cd server && uv run pytest tests/integration/test_smoke.py`

**Requirements covered:** —

---

### Track B: Server integration rows [server]

#### Task 7.2: Ingestion integration rows

**Prerequisites:** Task 7.1
**Conflicts with:** None
**Parallel with:** Tasks 7.3–7.6, 7.7–7.10
**Package:** `server/tests/integration`

**Objective:** Cover the §8.3 ingestion rows end to end through the real app.

**Instructions:**
1. Create `server/tests/integration/test_ingest.py` with rows: a well-formed extraction returns
   parsed orders with derived windows; a page the model cannot read returns `unrecognized-page`; a
   payload over the ceiling returns `payload-too-large` **without any Bedrock call**; a Bedrock
   transport failure returns `upstream-unavailable`.
2. Assert on the response body's documented shape, not on an exception type.
3. Assert the extracted content never appears in any log record.
4. Reference: Low-Level Design §8.3; requirements FR-3.1.3, FR-3.1.4, FR-3.2.1, NFR-6.1.

**Verification:**
- `cd server && uv run pytest tests/integration/test_ingest.py`

**Requirements covered:** FR-3.1.3, FR-3.1.4, FR-3.2.1, NFR-6.1

---

#### Task 7.3: Next-step integration rows

**Prerequisites:** Task 7.1
**Conflicts with:** None
**Parallel with:** Tasks 7.2, 7.4–7.10
**Package:** `server/tests/integration`

**Objective:** Cover the §8.3 action rows, including the closed-vocabulary guarantee at the wire.

**Instructions:**
1. Create `server/tests/integration/test_next_step.py` with rows: a forced tool call returns each of
   the five action kinds in its valid shape; a text-only completion (the model answering without the
   forced tool) returns `upstream-unavailable` — the closed table of §4.2 has no separate code for a
   misbehaving model, and inventing one is exactly the drift the table exists to prevent; a transport
   failure returns `upstream-unavailable`; a tool input with an invented kind returns a validation
   error rather than being forwarded.
2. Assert the request the harness saw carried a `tool_choice` forcing the tool — the guarantee is in
   the request, so assert on the request, not only on the response.
3. Reference: Low-Level Design §8.3, §4.2; requirements FR-3.3.8; repo `AGENTS.md` rule 9.

**Verification:**
- `cd server && uv run pytest tests/integration/test_next_step.py`

**Requirements covered:** FR-3.3.8

---

#### Task 7.4: Eligibility and schedule integration rows

**Prerequisites:** Task 7.1
**Conflicts with:** None
**Parallel with:** Tasks 7.2, 7.3, 7.5–7.10
**Package:** `server/tests/integration`

**Objective:** Cover the §8.3 rows for the two gates that keep a booking honest.

**Instructions:**
1. Create `server/tests/integration/test_pickup_schedule.py` with rows: a serviceable address returns
   serviceable; a non-serviceable address returns **200 with the normal result body** carrying an
   explicit negative and `address-not-serviceable` — the §4.2 error shape is asserted *absent* here,
   because FR-3.4.1 makes a negative answer a successful response; scheduling after a successful check
   returns a confirmation and the day USPS named; **a schedule whose eligibility call refuses returns
   the §4.2 error body with `address-not-serviceable` and the mock records no schedule call**; a
   schedule carrying `label_printed` false returns `label-not-printed`; a schedule whose `label_carrier`
   is not USPS returns `wrong-carrier-label`; a package location the adapter cannot serve returns
   `location-not-serviceable` **with `details.servable_locations`** so the client can re-ask from the
   reduced set (FR-3.4.8) rather than substitute one.
2. Assert the day in the response is the day the mock returned, including a case where it is not
   tomorrow.
3. Assert no response body and no log record contains an ETag.
4. Reference: Low-Level Design §8.3, §4.3; requirements FR-3.4.1, FR-3.4.2, FR-3.4.5, FR-3.4.6; repo
   `AGENTS.md` rules 3, 4, 5.

**Verification:**
- `cd server && uv run pytest tests/integration/test_pickup_schedule.py`

**Requirements covered:** FR-3.4.1, FR-3.4.4, FR-3.4.5, FR-3.4.7, FR-3.4.8

---

#### Task 7.5: Refresh and cancel integration rows

**Prerequisites:** Task 7.1
**Conflicts with:** None
**Parallel with:** Tasks 7.2–7.4, 7.6–7.10
**Package:** `server/tests/integration`

**Objective:** Cover the §8.3 cancellation rows, including the refresh-then-cancel ordering.

**Instructions:**
1. Create `server/tests/integration/test_pickup_cancel.py` with rows: a cancel a day later refreshes
   then cancels, in that order per the mock's call log; a cancel whose refresh reveals the box has
   already been collected returns a **successful** body saying so **and issues no cancel call** — this
   is a result, not one of the §4.2 reasons; a cancel attempted against a stale ETag returns
   `etag-expired`, which is the endpoint's instruction to refresh again rather than a dead end; a
   refresh failure returns `upstream-unavailable` and issues no cancel; a refresh returning a fresh
   ETag is used for the cancel, and that ETag appears in no response body and no log record.
2. Reference: Low-Level Design §8.3, §4.5; requirements FR-3.4.6, FR-3.4.7; repo `AGENTS.md` rule 3.

**Verification:**
- `cd server && uv run pytest tests/integration/test_pickup_cancel.py`

**Requirements covered:** FR-3.4.6, FR-3.4.7

---

#### Task 7.6: Cross-cutting integration rows

**Prerequisites:** Task 7.1
**Conflicts with:** None
**Parallel with:** Tasks 7.2–7.5, 7.7–7.10
**Package:** `server/tests/integration`

**Objective:** Cover the §8.3 rows that belong to no single endpoint — the error shape, the version
gate, request-id isolation, deadlines, and CORS.

**Instructions:**
1. Create `server/tests/integration/test_cross_cutting.py` with rows:
   - every `reason` in the taxonomy renders in the one documented body shape, driven by a table over
     the error classes so a new class without a rendering fails here;
   - a below-floor client version is rejected on **two different endpoints**, and in both the mock
     records no carrier call and the Bedrock transport saw no request;
   - two concurrent requests carry distinct request ids and neither's id appears in the other's log
     records;
   - an upstream that exceeds the request deadline returns `upstream-unavailable` rather than hanging;
   - `GET /health` needs no version header and makes no upstream call;
   - a configured origin gets a CORS header and an unconfigured one does not.
2. Reference: Low-Level Design §8.3, §6.2, §7.1; requirements §4.2, §5.1, NFR-6.1, NFR-6.4, NFR-6.7.

**Verification:**
- `cd server && uv run pytest tests/integration`

**Requirements covered:** §4.2, §5.1, NFR-6.1, NFR-6.4, NFR-6.7

---

### Track C: Extension driver flows [extension]

#### Task 7.7: The return-method choice flow

**Prerequisites:** Task 6.8, Task 3.14
**Conflicts with:** Tasks 7.8–7.10 (`src/driver/driver.ts`)
**Parallel with:** Tasks 7.1–7.6 (server)
**Package:** `extension/src/driver`

**Objective:** Implement §4.6 — present every return method with its price, let the user choose, and
persist the choice in the same `transact` as the transition.

**Instructions:**
1. On reaching a return-method page, read every option and its price through the adapter and
   transition to `AwaitingLabelChoice`, persisting the options.
2. **Present all of them, with prices.** Never auto-select, never prefer the one that happens to
   produce a USPS label. `// dev-note:` repo rule 6: buying a paid label out of the user's refund to
   satisfy our own pickup precondition is the exact failure this rule exists to prevent.
3. An option whose price could not be read is presented as **unreadable**, not as free and not
   omitted.
4. On the user's choice, `AwaitingLabelChoice --> Driving` in **one** `transact` that also writes
   `session.chosen_option`. This is FR-3.3.5's source one, and §4.6 opens a window of two transitions
   before it is read.
5. The free drop-off branch (a QR code, no printable label) is a legitimate success: it transitions
   toward `DroppedOff` with `chosen_option` left null and skips the pickup step entirely (rule 4).
6. Unit tests: all options are presented with prices; an unreadable price is marked, not defaulted; a
   choice writes `chosen_option` and the state in one `set`; the free drop-off branch leaves
   `chosen_option` null; no code path selects an option without a user action.
7. Reference: Low-Level Design §4.6, §3.5; requirements FR-3.3.4, FR-3.3.5; repo `AGENTS.md` rules 4, 6.

**Verification:**
- `cd extension && bun run test tests/driver/choice.test.ts`

**Requirements covered:** FR-3.3.4, FR-3.3.5

---

#### Task 7.8: `derive_label_carrier` — three sources, in order

**Prerequisites:** Task 7.7
**Conflicts with:** Tasks 7.7, 7.9, 7.10 (`src/driver/driver.ts`)
**Parallel with:** Tasks 7.1–7.6
**Package:** `extension/src/driver`

**Objective:** Determine which carrier's postage is on the box, from three ordered sources, never
defaulting.

**Instructions:**
1. Implement `derive_label_carrier(session, adapter, label_dom)` trying, **in this order**:
   1. `adapter.carrier_by_option[session.chosen_option]` — the user's own choice, read back from the
      persisted session;
   2. `adapter.label_carrier_patterns` matched against the label page **locally**; the label DOM is
      never transmitted for this;
   3. asking the user.
2. **A miss is not a value.** There is no USPS default — a wrong answer here books a USPS pickup for a
   UPS box that no carrier will collect (rule 4). `// dev-note:` it.
3. If all three fail, the return proceeds to `LabelPrinted` with the carrier undetermined and **no
   pickup is offered**. An undetermined carrier is a successful return, just not a pickup.
4. Unit tests: source one resolves when `chosen_option` is present; source two resolves when
   `chosen_option` is null and the patterns match; source three is reached only when both miss;
   **when `chosen_option` is present, source two is never consulted** (assert the pattern matcher was
   not called — this is what makes the ordering observable); all three missing yields undetermined and
   offers no pickup; the label DOM never reaches the API client.
5. Reference: Low-Level Design §4.6, §3.5; requirements FR-3.3.5; repo `AGENTS.md` rule 4.

**Verification:**
- `cd extension && bun run test tests/driver/carrier.test.ts`

**Requirements covered:** FR-3.3.5

---

#### Task 7.9: Print affirmation, pickup offer, and consent

**Prerequisites:** Task 7.8, Task 4.10, Task 4.13
**Conflicts with:** Tasks 7.7, 7.8, 7.10 (`src/driver/driver.ts`)
**Parallel with:** Tasks 7.1–7.6
**Package:** `extension/src/driver`

**Objective:** Record that the user says the label is printed, gate the pickup offer on the derived
carrier, and persist consent before the booking call.

**Instructions:**
1. FR-3.3.6: the print affirmation is the **user's statement**, recorded as a field on the return —
   it is not a state transition. The extension cannot observe a printer; pretending otherwise would
   put a fact in the state machine that nothing can verify. `// dev-note:` this.
2. Offer a pickup **only** when the derived carrier is USPS **and** the label is affirmed printed.
   Undetermined carrier, non-USPS carrier, or unaffirmed label each mean no offer, with a reason the
   popup can show.
3. Before calling `POST /pickups`, call eligibility for the stored address (rule 3). Ineligible means
   offer drop-off or a priced alternative with its price — never a silent paid escalation (rule 6).
4. **`PickupRepository.save_intent` writes the consent stamp and the address before the network
   call** (FR-3.4.5a), then `promote` attaches the confirmation and day on response. A lost response
   therefore leaves a consented, unpromoted record rather than losing the consent.
5. FR-3.4.8: a refused location is re-asked — the user supplies a different location and the flow
   retries eligibility rather than abandoning the pickup.
6. Copy rule: name the **day** USPS returned, never a time window (rule 5). The driver passes the day
   through; the popup renders it.
7. Unit tests: affirmation writes a field and no transition; a non-USPS carrier offers no pickup; an
   undetermined carrier offers no pickup; eligibility precedes schedule in the API call log; a lost
   schedule response leaves consent recorded; a location refusal re-asks and re-checks; no code path
   schedules without a prior successful check.
8. Reference: Low-Level Design §4.3, §4.6; requirements FR-3.3.6, FR-3.4.1–FR-3.4.5a, FR-3.4.8.

**Verification:**
- `cd extension && bun run test tests/driver/pickup.test.ts`

**Requirements covered:** FR-3.3.6, FR-3.4.1, FR-3.4.2, FR-3.4.3, FR-3.4.4, FR-3.4.5, FR-3.4.5a, FR-3.4.7, FR-3.4.8, NFR-6.2

---

#### Task 7.10: Cancellation orchestration

**Prerequisites:** Task 7.9
**Conflicts with:** Tasks 7.7–7.9 (`src/driver/driver.ts`)
**Parallel with:** Tasks 7.1–7.6
**Package:** `extension/src/driver`

**Objective:** Implement §4.5 in the worker — cancel a booked pickup through the server, handling the
collected and refused outcomes as distinct results.

**Instructions:**
1. Implement `cancel_pickup(pickup_id)`: call `DELETE /pickups/{id}`; the server refreshes then
   cancels, so the extension holds no ETag and never sends one.
2. On success, settle the local record. On an **already-collected** result — the server's refresh
   found the box gone — **do not report a cancellation**: mark it collected, move the owning
   `RETURN_REQUEST` to `LabelPrinted` per FR-3.4.6, and tell the user it has already been picked up.
   On `upstream-unavailable`, leave the record unsettled so a retry is possible, and say the pickup
   may still happen. On `etag-expired`, the server refreshes and retries internally; the extension
   holds no ETag and has nothing to do with it.
3. The local record is updated **after** the server confirms, never optimistically. A pickup that
   exists at USPS and not in our store is the failure mode this ordering avoids.
4. Unit tests: a successful cancel settles the record and leaves the `RETURN_REQUEST` at `LabelReady`
   (FR-3.4.6 — cancelling a pickup is not a terminal state for the return); an already-collected result
   marks collected, reports collected rather than cancelled, and moves the request to `LabelPrinted`;
   a refusal leaves the record unsettled; the extension sends no ETag on any path; a cancel is not
   retried automatically.
5. Reference: Low-Level Design §4.5; requirements FR-3.4.6, FR-3.4.7; repo `AGENTS.md` rule 3.

**Verification:**
- `cd extension && bun run test tests/driver/cancel.test.ts`

**Requirements covered:** FR-3.4.6, FR-3.4.7

---

### Batch 7 Commit Checkpoint

After all tracks complete:
- [ ] Server unit and integration tests pass: `cd server && uv run pytest`
- [ ] Extension tests pass: `cd extension && bunx tsc --noEmit && bun run test`
- [ ] **The server is functionally complete** — every §8.3 server row is green.
- [ ] The extension's return flow is complete from scan to printed label to booked pickup to
      cancellation, all unit-tested against the fake browser.

---

## Batch 8: Entrypoints and Wiring

### Track A: Content script and service worker [extension]

#### Task 8.1: `entrypoints/content.ts`

**Prerequisites:** Task 3.9, Task 3.13, Task 5.6
**Conflicts with:** None
**Parallel with:** Task 8.3 (different files, but 8.3 needs 8.2's router)
**Package:** `extension/entrypoints`

**Objective:** Recognise an order page, wait for it to settle, extract, and hand the payload to the
worker — doing nothing on a page no adapter claims.

**Instructions:**
1. Create `extension/entrypoints/content.ts` registered for the optional host permissions only.
2. Resolve the adapter via `registry.for_url(location.href)`. **No adapter means do nothing** — no
   extraction, no message, no observer left running.
3. Wait for the page to settle before extracting: a `MutationObserver` with a debounce and a hard
   ceiling, since retailer order pages render asynchronously and extracting too early yields a
   skeleton.
4. Call `extract` (Task 3.9) and send the payload to the worker through `src/messaging/`.
5. The content script performs **no** network call. It has no server client; the worker owns egress.
6. Unit tests in a jsdom environment: an unclaimed URL produces no message and disconnects the
   observer; a claimed URL extracts once after settling, not once per mutation; the debounce ceiling
   fires even on a page that never settles.
7. Reference: Low-Level Design §4.1, §7.2; requirements FR-3.1.1, FR-3.1.2.

**Verification:**
- `cd extension && bun run test tests/entrypoints/content.test.ts`

**Requirements covered:** FR-3.1.1, FR-3.1.2, FR-3.1.3

---

#### Task 8.2: `entrypoints/background.ts` — the worker wiring graph

**Prerequisites:** Task 8.1, Task 7.10, Task 5.6, Task 4.12, Task 3.17
**Conflicts with:** None
**Parallel with:** Task 8.3 (which depends on this)
**Package:** `extension/entrypoints`

**Objective:** Construct the object graph §7.2 specifies at worker start, register the routers and
listeners, and implement the ingestion flow of §4.1.

**Instructions:**
1. Create `extension/entrypoints/background.ts`. On every worker start, construct in §7.2's order:
   storage coordinator → repositories → session store → API client → adapter registry → tab factory →
   executor → prompt → `ReturnDriver`.
2. **Construction is cheap and happens on every start.** The worker dies after ~30s idle, so this runs
   constantly; nothing in the graph may do I/O at construction time. `// dev-note:` it.
3. Register `on_internal` / `on_external` handlers from `src/messaging/`, `chrome.tabs.onRemoved` (so
   a closed tab reaches the driver), and the permission listeners from Task 3.17.
4. Implement §4.1 ingestion: receive the extracted payload → `POST /orders/ingest` → validate →
   `evict_to_fit` then `OrderRepository.upsert` inside one `transact` → notify the popup.
5. On worker start, call `ReturnDriver.resume()` — if a session was persisted, the new worker picks
   the flow back up.
6. **No `chrome.permissions.request` here** (Task 3.17's guard throws) — the worker has no gesture.
7. Unit tests: construction performs no storage or network call; an ingest message stores validated
   orders; an oversize ingest evicts before storing and stays under cap; worker start with a live
   session calls `resume`; worker start with no session does not; a closed tab reaches the driver.
8. Reference: Low-Level Design §7.2, §4.1, §4.4; requirements FR-3.1.4, FR-3.1.5, NFR-6.3.

**Verification:**
- `cd extension && bun run test tests/entrypoints/background.test.ts`

**Requirements covered:** FR-3.1.4, FR-3.1.5, NFR-6.3

---

### Track B: Popup surfaces [extension]

#### Task 8.3: Popup shell, ranked list, scan gesture, permission offer

**Prerequisites:** Task 8.2, Task 3.11, Task 3.17
**Conflicts with:** Tasks 8.4, 8.5 (same popup shell and route table)
**Parallel with:** —
**Package:** `extension/entrypoints/popup`

**Objective:** Build the popup's shell and its first screen — the ranked list, the "Scan this page"
gesture, and the standing-permission offer that comes **after** the user has seen it work.

**Instructions:**
1. Create `extension/entrypoints/popup/` with the shell and a small route table the next two tasks
   extend.
2. Render the ranked list from stored orders through `src/ranking/` (Task 3.11), with the deadline and
   the urgency ordering; items with an undetermined window are shown as undetermined, not as "no
   deadline".
3. **"Scan this page"** is the first-run path: `activeTab` grants access only on a gesture, so the
   button click is what makes injection legal. There is no injection on page load and no `<all_urls>`
   (rule 8).
4. After a successful scan, **then** offer the standing host permission for that retailer, in context.
   Call `permissions.request_standing` from here — the popup is the only place with a gesture.
5. A declined permission is a normal state: the list still works and the scan button remains the path.
   Never re-prompt automatically.
6. Unit tests: the list renders in ranked order; the scan button injects only on click; the permission
   offer appears only after a successful scan; a decline leaves the scan path working and does not
   re-prompt.
7. Reference: Low-Level Design §7.2; requirements FR-3.2.3, FR-3.7.2, FR-3.7.3; repo `AGENTS.md`
   rule 8.

**Verification:**
- `cd extension && bun run test tests/popup/list.test.ts`

**Requirements covered:** FR-3.2.2, FR-3.2.3, FR-3.6.1, FR-3.7.2, FR-3.7.3

---

#### Task 8.4: Popup return surfaces — choice, affirmation, stuck

**Prerequisites:** Task 8.3
**Conflicts with:** Tasks 8.3, 8.5 (popup shell and route table)
**Parallel with:** —
**Package:** `extension/entrypoints/popup`

**Objective:** Render the screens the return flow pauses on: the return-method choice, the print
affirmation, and the stalled/handed-off states.

**Instructions:**
1. **Return-method choice:** list every option with its price, with no option pre-selected and no
   visual default. An unreadable price shows as unreadable — never as free, never hidden (rule 6).
2. **Print affirmation:** an explicit "I printed it" the user asserts; the copy must not imply the
   extension checked (FR-3.3.6).
3. **Stalled:** explain what the flow could not do and hand control back, including the case where the
   egress scan blocked a fallback — the user is told the page could not be sent, not given a generic
   error.
4. **Handed off:** the tab is gone; say so and offer to start again.
5. Unit tests: every option renders with its price; nothing is pre-selected; an unreadable price
   renders as unreadable; the affirmation copy contains no claim of verification; a stalled return
   renders its reason.
6. Reference: Low-Level Design §4.6, §4.2; requirements FR-3.3.4, FR-3.3.6, FR-3.3.7, FR-3.3.8.

**Verification:**
- `cd extension && bun run test tests/popup/return.test.ts`

**Requirements covered:** FR-3.3.1, FR-3.3.3, FR-3.3.4, FR-3.3.6, NFR-6.4

---

#### Task 8.5: Popup pickup, calendar, and clear-all surfaces

**Prerequisites:** Task 8.4, Task 3.12, Task 4.12
**Conflicts with:** Tasks 8.3, 8.4 (popup shell and route table)
**Parallel with:** —
**Package:** `extension/entrypoints/popup`

**Objective:** Render the pickup confirmation with its consent stamp and day-not-window copy, the
calendar offer, and the clear-all that warns about a live booking.

**Instructions:**
1. **Confirmation screen:** shows the address, the carrier whose postage is on the box, and an
   explicit consent control. Consent is captured here and recorded before the booking call
   (FR-3.4.5a). The screen appears only when a pickup is actually being offered.
2. **Simulated bookings are labelled as simulated.** A confirmation number carrying the
   `MockCarrierAdapter` prefix (Task 4.14, published in `contracts/`) renders with a
   **"simulated — no carrier was contacted"** marker on the confirmation screen and anywhere else the
   booking is shown.
   - **Why this exists.** Under `CARRIER_ADAPTER=mock` — requirements §5.1's default until USPS
     access lands, and what every demo and Task 8.6's acceptance run books against — the extension
     stores a fabricated confirmation number and writes an NFR-6.2 `ConsentStamp` for a pickup that
     was never booked. §5.1 names this failure but guards only production. This screen is the one
     place in the product that would otherwise state something false, and it is the screen most
     likely to be shown to other people. The product's governing rule is that a derived thing is
     never presented as authoritative; this is that rule applied to itself. Decision D22.
   - Detect the prefix, not the environment. A build-time flag would be wrong whenever a dev build
     talks to a real carrier or a prod build degrades to the mock — the confirmation number is the
     thing that actually knows.
3. **Copy rule, enforced by a test:** the collection copy names a **day**, never a time window
   (rule 5). Add an assertion that the rendered string contains no window-shaped phrasing.
4. **Ineligible / refused:** show the carrier's reason and offer drop-off or a priced alternative with
   its price stated. Never present a paid option as if it were the free one (rule 6).
5. **Cancel:** invokes the driver's cancellation; renders "already collected" as its own outcome, not
   as a failed cancel.
6. **Calendar offer:** open the template URL in a new tab, and offer the `.ics` as a fallback. If the
   tab fails to open, the `.ics` path still works — the reminder must not depend on one delivery
   mechanism. No Google scope is involved on either path (rules 1, 2).
7. **Clear all data:** if `clear_all` reports an unsettled pickup, warn that a booked USPS pickup will
   still happen regardless of what is deleted here, and require a second confirmation.
8. Unit tests: the confirmation shows the address and carrier and requires consent; consent is
   recorded before the booking call is issued; **a prefixed confirmation number renders the simulated
   marker and an unprefixed one does not**; the collection copy names a day and matches no window
   phrasing; an ineligible result offers alternatives with prices; cancel renders collected as its own
   outcome; a failed calendar tab still offers the `.ics`; clear-all with an unsettled pickup warns
   and double-confirms.
9. Reference: Low-Level Design §4.3, §4.5, §3.4; requirements §5.1, FR-3.4.3, FR-3.4.5, FR-3.4.5a,
   FR-3.4.6, FR-3.4.7, FR-3.4.8, FR-3.5.1, FR-3.5.3, FR-3.5.5, NFR-6.2; decision D22.

**Verification:**
- `cd extension && bun run test tests/popup`

**Requirements covered:** FR-3.4.3, FR-3.4.5, FR-3.4.5a, FR-3.4.6, FR-3.4.7, FR-3.4.8, FR-3.5.1, FR-3.5.3, FR-3.5.5, NFR-6.1

---

### Gate: Manual acceptance [extension]

#### Task 8.6: Walk the whole product by hand in a real browser

**Prerequisites:** Task 8.5
**Conflicts with:** None
**Parallel with:** —
**Package:** `docs/`

**Objective:** Nothing else in this plan runs the built extension in a real browser. Batch 9 drives an
assembled extension under `vitest` against a fake `chrome`; Task 10.1 inspects a bundle statically.
The fake browser is a model of Chrome written by the same people writing the code it validates, so it
cannot catch the class of defect where the model is wrong. Decision D23.

**Why the steps are written down.** An unwritten manual test is not repeatable and its failure is not
reportable. This step list is also the demo script.

**Instructions:**
1. Write `docs/acceptance.md` with the step list below, each step paired with the **observation that
   means it passed** — not "it works", but what specifically should be on screen.
2. Run it: `cd extension && bun run build`, then load `.output/chrome-mv3` unpacked in Chrome with
   `docker compose up --build` serving the API and `CARRIER_ADAPTER=mock`.
3. The steps:
   1. **Load unpacked.** The extension ID matches the one Task 1.4 pinned. Only `activeTab`,
      `scripting` and `storage` are requested at install; Chrome shows no host-permission warning.
   2. **Open an order page and scan.** Nothing injected before the gesture. After it, the popup lists
      the orders with return windows, ordered by urgency.
   3. **Accept the standing permission offer.** It appears *after* the first successful scan, never
      before.
   4. **Start a return and drive to the label choice.** The methods are listed with prices; the free
      printable-label option is identifiable.
   5. **Confirm the choice, then affirm the print.** The return does not advance to `LabelPrinted`
      without the affirmation.
   6. **Book the pickup.** Consent is captured before the call. The confirmation screen names a
      **day**, not a window — and carries the **"simulated"** marker, because this is the mock
      carrier (Task 4.14, decision D22). *A confirmation number rendered without that marker here is
      a failure of this step, not a cosmetic issue.*
   7. **Open the calendar template.** A new tab opens a prefilled Google Calendar event. No Google
      sign-in, no OAuth consent screen appears at any point — if one does, stop and treat it as a
      defect against rules 1 and 2.
   8. **Cancel the pickup.** The pickup returns to a cancelled state and the return's own state is
      unaffected.
   9. **Reload the extension mid-return** and confirm the driver rehydrates rather than restarting.
   10. **Clear all data** with a live booking and confirm the double-confirmation warns that the
       booked pickup still happens.
4. Record the result — pass, or the step that failed and what was observed instead — with the date
   and the Chrome version. A failed step blocks the Batch 8 checkpoint.
5. Reference: requirements FR-3.1.x, FR-3.3.x, FR-3.4.x, FR-3.5.x, FR-3.7.x; repo `AGENTS.md` rules
   1, 2, 5, 6, 8; decisions D22, D23.

**Verification:**
- `docs/acceptance.md` exists, and its most recent run is recorded as passing with a date.

**Requirements covered:** — (manual confirmation of the FRs the automated suites assert)

---

### Batch 8 Commit Checkpoint

After all tracks complete:
- [ ] Extension builds and tests pass: `cd extension && bun run build && bun run test`
- [ ] The unpacked extension loads in Chrome and a full return can be walked by hand against the PoC
      retailer, with `docker compose up --build` serving the API.
- [ ] **Task 8.6's step list has been run in a real browser and recorded as passing.** A green Batch 9
      against the fake browser does not substitute for this.
- [ ] A mock-backed booking renders as simulated, in the browser, observed by a person.
- [ ] Nothing injects on page load; the first scan is a gesture and the standing permission is offered
      after it.

---

## Batch 9: Extension Integration Tests

### Track A: Harness [extension]

#### Task 9.1: End-to-end extension test harness

**Prerequisites:** Task 8.5
**Conflicts with:** None
**Parallel with:** —
**Package:** `extension/tests/integration`

**Objective:** Wire the **real** object graph over the fake browser, so §8.3's extension rows exercise
the same construction path `background.ts` uses rather than a test-only assembly.

**Instructions:**
1. Create `extension/tests/integration/harness.ts` building the graph by calling the same factory
   `background.ts` calls, over the Task 2.6/2.7 fakes and a scripted API double.
2. Expose: `kill_worker()` (drops the graph and rebuilds it from storage alone — the actual meaning of
   a worker death), `advance_clock(ms)`, `open_page(fixture)`, `click_popup(...)`, and an API call log.
3. `kill_worker()` must rebuild through the real factory. A harness that keeps a reference alive makes
   every worker-death row pass vacuously, which is precisely the failure §8.3's rows exist to catch.
4. Verify with one smoke row: scan a fixture page, see an order stored, kill the worker, and read the
   order back.
5. Reference: Low-Level Design §8.1, §8.3, §7.2.

**Verification:**
- `cd extension && bun run test tests/integration/smoke.test.ts`

**Requirements covered:** —

---

### Track B: Integration rows [extension]

#### Task 9.2: Ingestion and permission rows

**Prerequisites:** Task 9.1
**Conflicts with:** None
**Parallel with:** Tasks 9.3–9.7
**Package:** `extension/tests/integration`

**Objective:** Cover §8.3's first-run, ingestion and storage-pressure rows.

**Instructions:**
1. Create `tests/integration/ingestion.test.ts` with rows: first run scans on a gesture and no
   injection happens before it; a declined permission leaves the scan path working; an ingested page
   produces a ranked list; a payload over the ceiling is refused before egress; ingestion under
   storage pressure evicts and stays under the cap without evicting an item with an active return.
2. Reference: Low-Level Design §8.3; requirements FR-3.1.1, FR-3.1.2, FR-3.1.3,
   FR-3.1.4, FR-3.1.5, FR-3.2.2, FR-3.2.3, FR-3.3.2, FR-3.7.2, FR-3.7.3.

**Verification:**
- `cd extension && bun run test tests/integration/ingestion.test.ts`

**Requirements covered:** FR-3.1.1, FR-3.1.2, FR-3.1.3, FR-3.1.4, FR-3.1.5, FR-3.2.2, FR-3.2.3, FR-3.3.2, FR-3.7.2, FR-3.7.3

---

#### Task 9.3: Driving rows

**Prerequisites:** Task 9.1
**Conflicts with:** None
**Parallel with:** Tasks 9.2, 9.4–9.7
**Package:** `extension/tests/integration`

**Objective:** Cover §8.3's rows for driving a return with and without the model.

**Instructions:**
1. Create `tests/integration/driving.test.ts` with rows: a full return completes on selectors alone
   with **zero** next-step calls; a return with one selector miss makes exactly one next-step call and
   completes; a page whose prices are unreadable presents them as unreadable and still lets the user
   choose; a fallback that exceeds `MODEL_FALLBACK_TIMEOUT_MS` lands `Stalled`; no return can be
   started without a user gesture.
2. Reference: Low-Level Design §8.3, §4.2; requirements FR-3.3.1, FR-3.3.3, FR-3.3.4,
   FR-3.3.7, FR-3.3.8.

**Verification:**
- `cd extension && bun run test tests/integration/driving.test.ts`

**Requirements covered:** FR-3.3.1, FR-3.3.3, FR-3.3.4, FR-3.3.7, FR-3.3.8

---

#### Task 9.4: State machine and terminal rows

**Prerequisites:** Task 9.1
**Conflicts with:** None
**Parallel with:** Tasks 9.2, 9.3, 9.5–9.7
**Package:** `extension/tests/integration`

**Objective:** Cover §8.3's state-machine rows — including **both** worker-termination rows, the
second of which exists because of finding CLASS-3.

**Instructions:**
1. Create `tests/integration/state-machine.test.ts` with rows:
   - free drop-off reaches `DroppedOff` with no pickup offered and no `chosen_option`;
   - an undetermined carrier reaches `LabelPrinted` with no pickup offered;
   - **worker terminated mid-flow** at `AwaitingConfirm` resumes at the same step;
   - **worker terminated between the choice and the label page** — the user picks a printable option,
     the worker is killed before the label page is reached, and the adapter fixture maps that option
     to a carrier whose `label_carrier_patterns` deliberately do **not** match. On rehydration,
     `chosen_option` is present and `derive_label_carrier` resolves through `carrier_by_option`.
     Because the patterns cannot produce the same answer, a fallthrough to source two is a **visible**
     failure rather than a silently equivalent one — that property is what makes the row meaningful,
     so the fixture must keep the mismatch;
   - a closed tab yields `HandedOff`;
   - a second return while one is live is refused;
   - a second return after an abort is allowed.
2. Reference: Low-Level Design §8.3, §8.4, §4.4, §4.6; requirements FR-3.3.5, FR-3.3.9, FR-3.3.10.

**Verification:**
- `cd extension && bun run test tests/integration/state-machine.test.ts`

**Requirements covered:** FR-3.3.5, FR-3.3.6, FR-3.3.9, FR-3.3.10

---

#### Task 9.5: Pickup rows

**Prerequisites:** Task 9.1
**Conflicts with:** None
**Parallel with:** Tasks 9.2–9.4, 9.6, 9.7
**Package:** `extension/tests/integration`

**Objective:** Cover §8.3's pickup rows, including the consent-survives-a-lost-response row.

**Instructions:**
1. Create `tests/integration/pickup.test.ts` with rows: a non-USPS label offers no pickup and says
   why; an ineligible address offers drop-off or a priced alternative and books nothing; an eligible
   address then a location refusal re-asks and re-checks; a schedule response lost in flight leaves a
   consented, unpromoted record and no double booking on the next attempt; consent is recorded before
   the booking call; the collection copy names a day and never a window.
2. Assert across all rows that **no schedule call is ever issued without a preceding successful
   eligibility check** for the same address.
3. Reference: Low-Level Design §8.3, §4.3; requirements FR-3.4.1–FR-3.4.5a, FR-3.4.8.

**Verification:**
- `cd extension && bun run test tests/integration/pickup.test.ts`

**Requirements covered:** FR-3.4.1, FR-3.4.2, FR-3.4.3, FR-3.4.4, FR-3.4.5, FR-3.4.5a, FR-3.4.7, FR-3.4.8, NFR-6.2

---

#### Task 9.6: Cancellation rows

**Prerequisites:** Task 9.1
**Conflicts with:** None
**Parallel with:** Tasks 9.2–9.5, 9.7
**Package:** `extension/tests/integration`

**Objective:** Cover §8.3's cancellation rows across a simulated day boundary.

**Instructions:**
1. Create `tests/integration/cancellation.test.ts` with rows: a pickup booked and cancelled a day
   later (clock advanced, not slept) settles locally after the server confirms; a cancel that finds
   the pickup already collected reports collected rather than cancelled; a cancel refused after a good
   refresh leaves the record unsettled and says the pickup may still happen.
2. Assert the extension sends no ETag on any path.
3. Reference: Low-Level Design §8.3, §4.5; requirements FR-3.4.6, FR-3.4.7.

**Verification:**
- `cd extension && bun run test tests/integration/cancellation.test.ts`

**Requirements covered:** FR-3.4.6, FR-3.4.7

---

#### Task 9.7: Platform rows

**Prerequisites:** Task 9.1
**Conflicts with:** None
**Parallel with:** Tasks 9.2–9.6
**Package:** `extension/tests/integration`

**Objective:** Cover §8.3's remaining platform rows — calendar fallback, store rebuild, version
rejection, and clear-all.

**The dashboard-messaging row is removed.** FR-3.6.3 is cut from PoC scope (decision D6), so there is
no external message path to assert against. Do not write a row for it; do not leave a skipped test
standing in for it — a skipped test is a claim that the feature exists and is untested, which is the
opposite of what is true.

**Instructions:**
1. Create `tests/integration/platform.test.ts` with rows: a calendar tab that fails to open still
   yields a working `.ics`; a store at a stale `schema_version` rebuilds and **keeps unsettled pickups
   and their booked addresses**; a server rejecting the client version surfaces an update prompt and
   stops the flow rather than retrying; **a message arriving from outside the extension is rejected
   without dispatch**; clear-all with a live pickup warns and, on confirmation, clears while telling
   the user the pickup still stands.
2. Reference: Low-Level Design §8.3, §5.1, §7.2; requirements FR-3.5.1, FR-3.5.2, FR-3.5.4, FR-3.5.5,
   FR-3.6.1; decision D6.

**Verification:**
- `cd extension && bun run test tests/integration`

**Requirements covered:** FR-3.1.5, FR-3.5.1, FR-3.5.2, FR-3.5.3, FR-3.5.4, FR-3.5.5, FR-3.6.1, NFR-6.3, NFR-6.4

---

### Batch 9 Commit Checkpoint

After all tracks complete:
- [ ] Extension unit and integration tests pass: `cd extension && bun run test`
- [ ] Server tests still pass: `cd server && uv run pytest`
- [ ] Every §8.3 row from the low-level design has a passing assertion, both worker-death rows
      included.

---

## Batch 10: Build Gates and Repository Checks

### Track A: Production bundle assertion

#### Task 10.1: Prod-bundle assertion in CI

**Prerequisites:** Task 8.5, Task 1.4 (the two pinned keys exist and their IDs are recorded)
**Conflicts with:** None
**Parallel with:** Tasks 10.2, 10.3
**Package:** `extension`

**Objective:** Make "a dev value shipped to production" a failed build rather than a discovery.

**Instructions:**
1. Add `extension/scripts/assert-prod-bundle.ts` run after `wxt build --mode production`, scanning
   `.output/chrome-mv3/` for: `localhost`, `127.0.0.1`, any `http:` (not `https:`) URL, and any origin
   not in the allowed set.
2. **Assert the manifest `key` is the prod key, not the dev one.** Task 1.4 generates both and records
   both derived extension IDs in `extension/AGENTS.md`; a production bundle carrying the dev key
   produces the dev extension ID, which the prod Function URL's single-origin CORS allowlist will
   refuse — so every request from the shipped extension fails, and it fails at the network layer
   where the cause is least obvious. Compare against the recorded prod ID.
3. Also assert the built manifest's permission array is exactly `activeTab`, `scripting`, `storage`,
   that `<all_urls>` appears nowhere, and that **`externally_connectable` is absent** (decision D6) —
   the same assertions as Task 1.2, but against the **built** artefact, which is the one that ships.
4. Wire it into the `build` script so it cannot be skipped by forgetting a separate command.
5. Reference: Low-Level Design §7.2; requirements FR-3.7.1, NFR-6.6; decisions D6, D20.

**Verification:**
- `cd extension && bun run build` — fails if a forbidden string is present (verify by temporarily
  pointing `API_BASE_URL` at localhost in a production build).

**Requirements covered:** FR-3.7.1, NFR-6.5, NFR-6.6

---

### Track B: Citation sweep

#### Task 10.2: Requirement citation sweep

**Prerequisites:** Task 9.7, Task 7.6
**Conflicts with:** None
**Parallel with:** Tasks 10.1, 10.3
**Package:** repository root

**Objective:** Close §9 Q4 with a script rather than a habit: every requirement is cited by some test,
every citation names a requirement that exists, and every configuration constant the code uses is one
the requirements actually define.

**Instructions:**
1. Add `scripts/citation-sweep.sh` that greps **both directions**:
   - every `FR-` and `NFR-` id in `design/boomerang-requirements.md` appears in at least one test file
     across `server/tests/` and `extension/tests/`;
   - every `FR-`/`NFR-` id cited in a test file exists in the requirements.
2. **Sweep configuration-parameter names too.** Every `SCREAMING_SNAKE_CASE` constant read from
   configuration in `server/app/` or `extension/src/` must appear in requirements §5.1 or §5.2, and
   every parameter those sections define must be referenced somewhere in the code.
   - **Why this half exists.** This plan shipped three wrong constant names for months of drafting:
     `PAYLOAD_CEILING_BYTES` and `API_TIMEOUT_MS` appear in no design document, and
     `API_RETRY_BUDGET_MS` was specified upstream and absent from the plan entirely — so a retry
     budget would simply never have been built. An identifier sweep catches a missing requirement
     citation but not an invented constant, and **the invented constant is the one that compiles**.
     Decision D18.
   - Maintain a small allowlist for genuinely local constants that are not configuration, with the
     reason inline for each.
3. Report the lists separately — an uncited requirement, an invented citation, an invented constant
   and an unused parameter are four different problems with four different fixes.
4. **Two known, deliberate exemptions**, both in an explicit allowlist with the reason inline:
   - **FR-3.6.2** — the phase-2 dashboard is out of this plan's scope per low-level design §1.
   - **FR-3.6.3** — dashboard-to-extension messaging is cut from PoC scope (decision D6): the
     dashboard origin it requires does not exist and high-level design §11 Q1 leaves the hostname
     undecided.
   Both are unplanned rather than satisfied, and the allowlist is what keeps them visible instead of
   quietly absent.
5. Wire the script into the `.github/workflows/ci.yml` repo job that Task 1.3 created with a
   conditional skip; that skip can now be removed.
6. Reference: Low-Level Design §8.4, §9 Q4; requirements §5.1, §5.2; decisions D6, D17, D18.

**Verification:**
- `bash scripts/citation-sweep.sh` — exits zero with FR-3.6.2 and FR-3.6.3 listed as exemptions and
  nothing else uncited.
- Introduce a constant named after nothing in §5.1 — the sweep fails; revert.
- CI runs the sweep unconditionally.

**Requirements covered:** — (this task verifies every other task's citations; FR-3.6.2 and FR-3.6.3 are the two allowlisted exemptions)

---

### Track C: Import boundary enforcement

#### Task 10.3: Enforce the module dependency graphs

**Prerequisites:** Task 8.5, Task 6.5
**Conflicts with:** None
**Parallel with:** Tasks 10.1, 10.2
**Package:** `server`, `extension`

**Objective:** Make the two dependency graphs in §2.1 and §2.2 enforced rather than documented. §10
declined to design this but recorded it as worth adding — this is that.

**Instructions:**
1. Server: add `import-linter` with contracts encoding §2.1 — `app.routes` may not import
   `app.carriers` or `app.bedrock`; `app.services` may not import `fastapi`; `app.models` imports
   nothing from `app` above it.
2. Extension: add an ESLint `no-restricted-imports` (or `eslint-plugin-boundaries`) config encoding
   §2.2 — the edges drawn in the graph are permitted and no others, with `src/types/` and
   `src/config.ts` exempt as universal leaves.
3. Add both to the test/lint scripts so a violating import fails CI.
4. Verify each rule fires by adding a violating import temporarily and confirming the failure, then
   removing it.
5. Reference: Low-Level Design §2.1, §2.2, §10.

**Verification:**
- `cd server && uv run lint-imports`
- `cd extension && bun run lint`

**Requirements covered:** NFR-6.3, NFR-6.5

---

### Batch 10 Commit Checkpoint

After all tracks complete:
- [ ] Full server suite: `cd server && uv run pytest && uv run lint-imports`
- [ ] Full extension suite: `cd extension && bun run build && bun run test && bun run lint`
- [ ] `bash scripts/citation-sweep.sh` passes
- [ ] `docker compose up --build` serves client :3000 and server :8000
- [ ] The architecture's invariants — permission posture, module boundaries, requirement coverage —
      are enforced by CI rather than by review attention.

---
## Task Status Tracker

This table is the single source of truth for task progress. Update status here as tasks are worked
on — there is no separate tracking file.

**Status values:** `[ ]` Not started | `[~]` In progress | `[x]` Completed

A task is eligible when its status is `[ ]`, every prerequisite is `[x]`, and no task named in its
**Conflicts** column is currently `[~]`. The conflict column is the one people skip: a conflicting
task is not a dependency — either order is fine — but two agents in it at once will collide on the
named file.

| Task | Description | Prerequisites | Conflicts | Status |
|------|-------------|---------------|-----------|--------|
| 0.1 | Walk the retailer return flow by hand; three go/no-go criteria | None | None | [ ] |
| 0.2 | File the USPS API access request | None | None | [ ] |
| 0.3 | Measure Bedrock parse and action latency | 0.1 | None | [ ] |
| 1.1 | Reconcile the existing server test harness with the §8 layout | None | None | [ ] |
| 1.2 | WXT project scaffold and MV3 manifest | None | 1.4 (`wxt.config.ts`) | [ ] |
| 1.3 | CI workflow for both workspaces | None | None | [ ] |
| 1.4 | Generate and pin the extension keypairs | 1.2 | 1.2 (`wxt.config.ts`) | [ ] |
| 1.5 | Extension coverage floor and pre-commit hook | 1.2 | None | [ ] |
| 2.1 | `app/errors.py` — the exception hierarchy | 1.1 | None | [ ] |
| 2.2 | `app/config.py` — `Settings` and fail-fast validation | 1.1 | None | [ ] |
| 2.3 | `app/logging.py` — redacting formatter and request-id binding | 1.1 | None | [ ] |
| 2.4 | `src/types/` — entities, session, and the state enums | 1.2 | None | [ ] |
| 2.5 | `src/config.ts` — build-time constants | 1.2 | None | [ ] |
| 2.6 | Fake `chrome.storage.local` | 1.2 | 2.7 (both add to `extension/tests/fakes/chrome.ts`) | [ ] |
| 2.7 | Fake `tabs`, `scripting`, `permissions`, worker lifecycle, and clock | 2.6 | 2.6 (both add to `extension/tests/fakes/chrome.ts`) | [ ] |
| 2.8 | Retailer DOM fixture harness | 1.2, **0.1** | None | [ ] |
| 3.1 | `app/models/common.py` — strict base model and the error body | 2.1 | 3.2, 3.3, 3.4 (all re-export through `app/models/__init__.py`) | [ ] |
| 3.2 | `app/models/orders.py` — ingestion payloads | 3.1 | 3.1, 3.3, 3.4 (`app/models/__init__.py`) | [ ] |
| 3.3 | `app/models/returns.py` — `ActionKind` and `ProposedAction` | 3.1 | 3.1, 3.2, 3.4 (`app/models/__init__.py`) | [ ] |
| 3.4 | `app/models/pickups.py` — address, eligibility, schedule, refresh, cancel | 3.1 | 3.1, 3.2, 3.3 (`app/models/__init__.py`) | [ ] |
| 3.5 | `app/carriers/base.py` — the `CarrierAdapter` protocol | 3.4 | None | [ ] |
| 3.6 | `app/middleware.py` — request id | 2.3 | None | [ ] |
| 3.7 | `app/services/window.py` — return-window derivation and urgency | 3.2 | None | [ ] |
| 3.8 | `app/deps.py` — app-state accessors and the `X-Boomerang-Client-Version` gate | 2.1, 2.2 | None | [ ] |
| 3.9 | `src/extract/` — subtree selection and sanitisation | 2.4, 2.5, 2.8 | 3.10 (both export from `src/extract/index.ts`) | [ ] |
| 3.10 | `src/extract/` — the fail-closed egress scan | 3.9 | 3.9 (`src/extract/index.ts`) | [ ] |
| 3.11 | `src/ranking/` — urgency ordering | 2.4 | None | [ ] |
| 3.12 | `src/calendar/` — template URL and `.ics` | 2.4, 2.5 | None | [ ] |
| 3.13 | `src/adapters/` — adapter type and registry | 2.4, **0.1** | 3.14 (both export from `src/adapters/index.ts`) | [ ] |
| 3.14 | The PoC retailer adapter | 3.13, 2.8, **0.1** | 3.13 (`src/adapters/index.ts`) | [ ] |
| 3.15 | `src/validation/` — the action validator | 2.4, 3.13 | 3.16 (both export from `src/validation/index.ts`) | [ ] |
| 3.16 | `src/validation/` — the order response validator | 2.4 | 3.15 (`src/validation/index.ts`) | [ ] |
| 3.17 | `src/permissions/` — two-tier permission state | 2.4, 2.7 | None | [ ] |
| 3.18 | `contracts/` — golden wire payloads both sides assert against | 3.4, 3.16 | None | [ ] |
| 4.1 | `app/prompts/` — tool schemas generated from the enums | 4.2, 3.2, 3.3 | 4.2 | [ ] |
| 4.2 | `app/bedrock.py` — settings-driven client and per-call-site models | 2.2 | 4.1 (both are the model boundary; 4.1 imports from this module) | [ ] |
| 4.3 | `app/carriers/usps/token.py` — OAuth token provider | 2.1, 2.2 | 4.4, 4.5 (`app/carriers/usps/__init__.py`) | [ ] |
| 4.4 | `app/carriers/usps/adapter.py` — `UspsAdapter` | 4.3, 3.5, 3.4 | 4.3, 4.5 (`app/carriers/usps/__init__.py`) | [ ] |
| 4.5 | `app/carriers/usps/scripted.py` — `ScriptedUspsAdapter` (test double) | 3.5, 3.4 | 4.3, 4.4 (`app/carriers/usps/__init__.py`) | [ ] |
| 4.6 | `src/storage/` — key layout, defensive read, rebuild, **and the barrel** | 2.4, 2.6 | 4.7 (`src/storage/index.ts`) | [ ] |
| 4.7 | `StorageCoordinator.transact` — the serialising queue | 4.6 | 4.6, 4.12 (`coordinator.ts`) | [ ] |
| 4.8 | `OrderRepository` | 4.7 | None — own file | [ ] |
| 4.9 | `ReturnRepository` | 4.7 | None — own file | [ ] |
| 4.10 | `PickupRepository` | 4.7 | None — own file | [ ] |
| 4.11 | `AddressRepository` and `SessionStore` | 4.7 | None — own files | [ ] |
| 4.12 | Coordinator cross-entity operations — eviction and clear-all | 4.8, 4.9, 4.10, 4.11 | 4.7 (`coordinator.ts`) | [ ] |
| 4.13 | `src/api/` — the typed server client | 3.15, 3.16, 2.5, 3.18 | None | [ ] |
| 4.14 | `app/carriers/mock.py` — `MockCarrierAdapter` (runtime stub) | 3.5, 3.4, 3.18 | None | [ ] |
| 5.1 | `app/services/ingest.py` — `IngestService` | 4.1, 4.2, 3.2, 3.7, 2.1 | None | [ ] |
| 5.2 | `app/services/action.py` — `ActionService` | 4.1, 4.2, 3.3, 2.1 | None | [ ] |
| 5.3 | `app/services/pickup.py` — `PickupService` | 3.5, 3.4, 2.1 | None | [ ] |
| 5.4 | `TabHandle`, `TabHandleFactory`, and `UserPrompt` | 2.4, 2.7 | 5.5 (both export from `src/driver/index.ts`) | [ ] |
| 5.5 | `StepExecutor` | 5.4, 3.15 | 5.4 (`src/driver/index.ts`) | [ ] |
| 5.6 | `src/messaging/` — internal message routing | 4.12, 2.4 | None | [ ] |
| 6.1 | `app/routes/health.py` | 1.1 | 6.2–6.4 (`app/routes/__init__.py`) | [ ] |
| 6.2 | `app/routes/orders.py` — `POST /orders/ingest` | 5.1, 3.8, 6.1 | 6.1, 6.3, 6.4 (`app/routes/__init__.py`) | [ ] |
| 6.3 | `app/routes/returns.py` — `POST /returns/next-step` | 5.2, 3.8, 6.2 | 6.1, 6.2, 6.4 (`app/routes/__init__.py`) | [ ] |
| 6.4 | `app/routes/pickups.py` — the four pickup endpoints | 5.3, 3.8, 6.3 | 6.1–6.3 (`app/routes/__init__.py`) | [ ] |
| 6.5 | `app/main.py` — lifespan, handlers, CORS, adapter selection, Mangum | 6.1, 6.2, 6.3, 6.4, 3.6, 4.4, 4.14, 4.2, 2.2 | None | [ ] |
| 6.6 | `ReturnDriver` — construction, `transition`, and `start` | 4.9, 4.11, 5.4, 5.5 | 6.7, 6.8 (all in `src/driver/driver.ts`) | [ ] |
| 6.7 | State machine edges and rehydration | 6.6 | 6.6, 6.8 (`src/driver/driver.ts`) | [ ] |
| 6.8 | Selector-first step loop and the model fallback | 6.7, 3.10, 4.13, 5.5 | 6.6, 6.7 (`src/driver/driver.ts`) | [ ] |
| I.1 | Replace the Terraform with the Lambda topology | 6.5, 1.4 | None | [ ] |
| I.2 | First deploy and a live smoke test | I.1 | None | [ ] |
| I.3 | Reconcile `UspsAdapter` against the USPS sandbox | I.1, 0.2, 4.4 | None | [ ] |
| 7.1 | Integration test harness | 6.5, 4.5 | None | [ ] |
| 7.2 | Ingestion integration rows | 7.1 | None | [ ] |
| 7.3 | Next-step integration rows | 7.1 | None | [ ] |
| 7.4 | Eligibility and schedule integration rows | 7.1 | None | [ ] |
| 7.5 | Refresh and cancel integration rows | 7.1 | None | [ ] |
| 7.6 | Cross-cutting integration rows | 7.1 | None | [ ] |
| 7.7 | The return-method choice flow | 6.8, 3.14 | 7.8–7.10 (`src/driver/driver.ts`) | [ ] |
| 7.8 | `derive_label_carrier` — three sources, in order | 7.7 | 7.7, 7.9, 7.10 (`src/driver/driver.ts`) | [ ] |
| 7.9 | Print affirmation, pickup offer, and consent | 7.8, 4.10, 4.13 | 7.7, 7.8, 7.10 (`src/driver/driver.ts`) | [ ] |
| 7.10 | Cancellation orchestration | 7.9 | 7.7–7.9 (`src/driver/driver.ts`) | [ ] |
| 8.1 | `entrypoints/content.ts` | 3.9, 3.13, 5.6 | None | [ ] |
| 8.2 | `entrypoints/background.ts` — the worker wiring graph | 8.1, 7.10, 5.6, 4.12, 3.17 | None | [ ] |
| 8.3 | Popup shell, ranked list, scan gesture, permission offer | 8.2, 3.11, 3.17 | 8.4, 8.5 (same popup shell and route table) | [ ] |
| 8.4 | Popup return surfaces — choice, affirmation, stuck | 8.3 | 8.3, 8.5 (popup shell and route table) | [ ] |
| 8.5 | Popup pickup, calendar, clear-all, and the simulated-booking marker | 8.4, 3.12, 4.12 | 8.3, 8.4 (popup shell and route table) | [ ] |
| 8.6 | Manual acceptance run in a real browser | 8.5 | None | [ ] |
| 9.1 | End-to-end extension test harness | 8.6 | None | [ ] |
| 9.2 | Ingestion and permission rows | 9.1 | None | [ ] |
| 9.3 | Driving rows | 9.1, **0.1** | None | [ ] |
| 9.4 | State machine and terminal rows | 9.1 | None | [ ] |
| 9.5 | Pickup rows | 9.1 | None | [ ] |
| 9.6 | Cancellation rows | 9.1 | None | [ ] |
| 9.7 | Platform rows | 9.1 | None | [ ] |
| 10.1 | Prod-bundle assertion in CI | 8.5, 1.4 | None | [ ] |
| 10.2 | Requirement and configuration citation sweep | 9.7, 7.6 | None | [ ] |
| 10.3 | Enforce the module dependency graphs | 8.5, 6.5 | None | [ ] |
**Eligible tasks** (nothing started yet — Batch 0 has no prerequisites):
- Task 0.1: Walk the retailer return flow by hand
- Task 0.2: File the USPS API access request

**Batch 0 gates only retailer-shaped work.** Tasks 1.1, 1.2, 1.3 have no prerequisites either and may
start immediately in parallel with Batch 0; what waits on Task 0.1 is 2.8, 3.13, 3.14, 7.7–7.10 and
the Batch 9 driving rows, marked in bold in the Prerequisites column above.

**Progress:** 0 / 91 tasks complete

---

## Critical Path

Two numbers matter here and they are not the same number. The **critical path** is the longest
sequential chain through the dependency graph — the floor if every task could start the instant its
prerequisites landed. The **makespan** is what this plan actually costs, because the plan imposes a
hard commit barrier at the end of every batch: no task in batch *n+1* starts until every task in
batch *n* has landed. Under a barrier the cost is not the longest chain, it is the sum of each
batch's own longest chain. The barrier is deliberate — it is what makes the checkpoints meaningful —
but it is not free, and the plan should say what it costs.

### The dependency floor

```
1.2  src/types and the WXT scaffold          [extension]
 →  2.4  entities, session, state enums       [extension/src/types]
 →  4.6  storage keys, rebuild, and barrel    [extension/src/storage]
 →  4.7  StorageCoordinator.transact          [extension/src/storage]
 →  4.9  ReturnRepository                     [extension/src/storage]
 →  6.6  ReturnDriver, transition, start      [extension/src/driver]
 →  6.7  state machine edges and rehydration  [extension/src/driver]
 →  6.8  selector-first loop, model fallback  [extension/src/driver]
 →  7.7  the return-method choice flow        [extension/src/driver]
 →  7.8  derive_label_carrier                 [extension/src/driver]
 →  7.9  print affirmation, pickup, consent   [extension/src/driver]
 →  7.10 cancellation orchestration           [extension/src/driver]
 →  8.2  background worker wiring graph       [extension/entrypoints]
 →  8.3  popup shell and ranked list          [extension/entrypoints/popup]
 →  8.4  popup return surfaces                [extension/entrypoints/popup]
 →  8.5  popup pickup, calendar, clear-all    [extension/entrypoints/popup]
 →  8.6  manual acceptance run                [browser]
 →  9.1  end-to-end extension harness         [extension/tests]
 →  9.7  platform rows                        [extension/tests]
 → 10.2  requirement and config sweep         [repo]
```

**Critical path length:** 20 tasks.

### The makespan the barrier actually buys

| Batch | Longest chain inside the batch | Slots |
|---|---|---|
| 0 | 0.1 → 0.3 | 2 |
| 1 | 1.2 → 1.4 | 2 |
| 2 | 2.6 → 2.7 | 2 |
| 3 | 3.1 → 3.2 → 3.3 → 3.4 → 3.5 (the `app/models/__init__.py` conflict serialises 3.1–3.4) | 5 |
| 4 | 4.6 → 4.7 → {4.8 ∥ 4.9 ∥ 4.10 ∥ 4.11} → 4.12 | 4 |
| 5 | 5.4 → 5.5 | 2 |
| 6 | 6.1 → 6.2 → 6.3 → 6.4 → 6.5 | 5 |
| 7 | 7.7 → 7.8 → 7.9 → 7.10 | 4 |
| 8 | 8.1 → 8.2 → 8.3 → 8.4 → 8.5 → 8.6 | 6 |
| 9 | 9.1 → any row | 2 |
| 10 | 10.1 ∥ 10.2 ∥ 10.3 | 1 |
| **Total** | | **~35** |

The deployment track (I.1 → I.2, with I.3 alongside) does not appear in that total: it opens once
Batch 6 lands and runs concurrently with Batches 7 through 9, and nothing in Batches 7–10 waits on
it. It is off the critical path by construction, which is the point of splitting it out of the batch
sequence rather than inserting it as Batch 6.5.

So the barrier costs roughly **15 slots** — 35 against a floor of 20. That is the price of being able
to say, at each checkpoint, that the tree is green and the working tree is clean. It is worth paying,
and it should not be discovered halfway through.

### Three things about the shape of this chain

**It runs entirely through the extension.** The server's own longest chain — 1.1 → 2.2 → 4.2 → 4.1 →
5.1 → 6.2 → 6.3 → 6.4 → 6.5 → 7.1 → 7.6 → 10.2 — is twelve tasks. The server finishes early and
waits. If only one agent is available, start it on the extension; if two, the server track is the
one that can afford to be interrupted.

**Driver and popup are a genuinely serial spine; storage is not.** Tasks 6.6–6.8 and 7.7–7.10 all
edit `src/driver/driver.ts`, and tasks 8.3–8.5 share the popup shell and its route table. Splitting
either would trade a real invariant — one state machine, one route table — for a scheduling
convenience, so the plan keeps the file whole and accepts the serial run. Storage looked like the
same thing and was not: Tasks 4.8–4.11 already wrote to four separate repository files, and the only
thing serialising them was the shared `src/storage/index.ts` barrel in the Conflicts column. Task
4.6 now writes that barrel complete and up front, exporting from modules that exist as stubs, so the
four repositories are mutually parallel. That single change takes Batch 4's pole from 7 slots to 4.
The test for whether a serial chain is real is whether the file has to stay whole; if it is only an
export list, it does not.

**Batch 0 is on the path in fact, if not in the diagram.** Task 0.1 has no dependents in Batch 1, so
it does not lengthen the chain above — but Tasks 2.8, 3.13, 3.14, the 7.7–7.10 flows and the Batch 9
driving rows all encode what it finds, and if it comes back negative on any of its three go/no-go
criteria the plan below it changes shape rather than slipping. Start it first and start it in
parallel with Batch 1; do not let it queue behind scaffolding.

---

## Parallelization Summary

| Batch | Tracks | Parallel? | Conflicts | Commit Coordination |
|-------|--------|-----------|-----------|---------------------|
| 0 | A, B, C | 0.1 ∥ 0.2; 0.3 after 0.1 | None — three documents | Runs alongside Batch 1; gate is a written go/no-go, not a green suite |
| 1 | A, B | A ∥ B | 1.2 ↔ 1.4 (`wxt.config.ts`) | 1.1, 1.2, 1.3 are all roots; 1.4 and 1.5 follow 1.2 |
| 2 | A, B, C, D + 3 extension tracks | server ∥ extension throughout | 2.6 ↔ 2.7 (`tests/fakes/chrome.ts`) | Serialise 2.6 → 2.7; everything else free |
| 3 | 11 tracks | server ∥ extension; most tracks mutually free | 3.1–3.4 (`app/models/__init__.py`); 3.9 ↔ 3.10 (`src/extract/index.ts`); 3.13 ↔ 3.14 (`src/adapters/index.ts`); 3.15 ↔ 3.16 (`src/validation/index.ts`) | Widest batch in the plan — 11 agents can work at once; 3.18 lands last because it needs 3.4 and 3.16 |
| 4 | A, B, C, C', D, E | server ∥ extension | 4.3–4.5 (`app/carriers/usps/__init__.py`); 4.1 ↔ 4.2 (model boundary); 4.6 → 4.7 → **{4.8 ∥ 4.9 ∥ 4.10 ∥ 4.11}** → 4.12 | The storage chain is still the batch's long pole, but four slots instead of seven |
| 5 | A, B, C, D, E | server ∥ extension | 5.4 ↔ 5.5 (`src/driver/index.ts`) | Server services are mutually independent |
| 6 | A, B | server ∥ extension | 6.1–6.4 (`app/routes/__init__.py`); **6.6 → 6.7 → 6.8 serial** (`src/driver/driver.ts`); 6.5 needs all four routes and 4.14 | Last batch where the two workspaces are still independent |
| — | Deployment | I.1 → I.2, I.3 ∥ I.2 | None — `infra/` is untouched by every other task | Opens after 6.5; runs concurrently with Batches 7–9 and gates nothing in them |
| 7 | A, B, C | server integration ∥ extension driver flows | 7.7–7.10 serial (`src/driver/driver.ts`); 7.2–7.6 mutually free | 7.2–7.6 are five agents on five files; 7.7–7.10 is one agent |
| 8 | A, B, Gate | Mostly serial | 8.3–8.5 share the popup shell and route table | 8.1 → 8.2 → 8.3 → 8.4 → 8.5 → 8.6; 8.6 is a human at a browser, not an agent |
| 9 | A, B | 9.2–9.7 all ∥ after 9.1 | None — one file each | Six agents can run the integration rows at once |
| 10 | A, B, C | 10.1 ∥ 10.2 ∥ 10.3 | None | CI enforcement; 10.2 needs 7.6 and 9.7 to have landed |

**Theoretical speedup, honestly stated.** Batches 3, 7 and 9 are the wide ones: 11, 5 and 6
simultaneous agents respectively. Ninety-one tasks over a 20-task dependency floor is a **4.5x**
ceiling — but that ceiling is unreachable under the commit barrier this plan imposes, and the number
that matters is 91 over a ~35-slot makespan, which is **~2.6x**. In practice the useful agent count
is **two to four**: one on the extension spine (which is the critical path and cannot be split), one
on the server, and one or two absorbing the wide batches as they open. Beyond four, agents queue
behind `src/driver/driver.ts` and the popup route table and add coordination cost without adding
throughput. Two of the 91 tasks — 0.2 and 8.6 — are not agent work at all: one is an email to USPS
and the other is a human driving a browser.

---

## Requirements Traceability

Every requirement in `design/boomerang-requirements.md` maps to the tasks that implement and test it.

Two conventions are load-bearing here. **Unit tests are not separate tasks** — the implementation
task is test-first, so its unit tests are written inside it; the "Unit Test Task(s)" column names the
same task and says `in-task` rather than inventing a phantom row. **Integration tests are separate
tasks**, because they exercise components no single task owns: Tasks 7.2–7.6 drive the assembled
FastAPI app, Tasks 9.2–9.7 drive the assembled extension, and Tasks 10.1 and 10.3 are CI assertions
about the shipped bundle and the module graph.

| Requirement | Implementation Task(s) | Unit Test Task(s) | Integration Test Task(s) |
|-------------|------------------------|-------------------|--------------------------|
| FR-3.1.1 | 3.13, 3.14, 8.1 | in-task (3.13, 3.14, 8.1) | 9.2 |
| FR-3.1.2 | 3.9, 8.1 | in-task (3.9, 8.1) | 9.2 |
| FR-3.1.3 | 3.2, 3.10, 6.2, 6.8, 8.1 | in-task (3.2, 3.10, 6.2, 6.8, 8.1) | 7.2, 9.2 |
| FR-3.1.4 | 3.2, 3.9, 4.1, 5.1, 6.2, 8.2 | in-task (3.2, 3.9, 4.1, 5.1, 6.2, 8.2) | 7.2, 9.2 |
| FR-3.1.5 | 4.6, 4.7, 4.8, 4.12, 8.2 | in-task (4.6, 4.7, 4.8, 4.12, 8.2) | 9.2, 9.7 |
| FR-3.2.1 | 3.2, 3.7, 5.1, 6.2 | in-task (3.2, 3.7, 5.1, 6.2) | 7.2 |
| FR-3.2.2 | 3.7, 3.11, 8.3 | in-task (3.7, 3.11, 8.3) | 9.2 |
| FR-3.2.3 | 3.11, 8.3 | in-task (3.11, 8.3) | 9.2 |
| FR-3.3.1 | 6.6, 8.4 | in-task (6.6, 8.4) | 9.3 |
| FR-3.3.2 | 3.17 | in-task (3.17) | 9.2 |
| FR-3.3.3 | 5.4, 5.5, 6.8, 8.4 | in-task (5.4, 5.5, 6.8, 8.4) | 9.3 |
| FR-3.3.4 | 3.14, 7.7, 8.4 | in-task (3.14, 7.7, 8.4) | 9.3 |
| FR-3.3.5 | 2.4, 3.14, 4.11, 6.7, 7.7, 7.8 | in-task (2.4, 3.14, 4.11, 6.7, 7.7, 7.8) | 9.4 |
| FR-3.3.6 | 7.9, 8.4 | in-task (7.9, 8.4) | 9.4 |
| FR-3.3.7 | 3.14, 5.2, 6.8 | in-task (3.14, 5.2, 6.8) | 9.3 |
| FR-3.3.8 | 2.4, 3.3, 3.15, 4.1, 5.2, 5.5, 6.3, 6.8 | in-task (2.4, 3.3, 3.15, 4.1, 5.2, 5.5, 6.3, 6.8) | 7.3, 9.3 |
| FR-3.3.9 | 2.4, 4.9, 5.4, 6.6, 6.7 | in-task (2.4, 4.9, 5.4, 6.6, 6.7) | 9.4 |
| FR-3.3.10 | 4.9, 6.6 | in-task (4.9, 6.6) | 9.4 |
| FR-3.4.1 | 2.1, 3.5, 4.4, 5.3, 6.4, 7.9 | in-task (2.1, 3.5, 4.4, 5.3, 6.4, 7.9) | 7.4, 9.5 |
| FR-3.4.2 | 7.9 | in-task (7.9) | 9.5 |
| FR-3.4.3 | 3.4, 4.4, 4.11, 5.3, 7.9, 8.5 | in-task (3.4, 4.4, 4.11, 5.3, 7.9, 8.5) | 9.5 |
| FR-3.4.4 | 5.3, 7.9 | in-task (5.3, 7.9) | 7.4, 9.5 |
| FR-3.4.5 | 3.4, 4.4, 4.10, 5.3, 7.9, 8.5 | in-task (3.4, 4.4, 4.10, 5.3, 7.9, 8.5) | 7.4, 9.5 |
| FR-3.4.5a | 3.4, 4.10, 7.9, 8.5 | in-task (3.4, 4.10, 7.9, 8.5) | 9.5 |
| FR-3.4.6 | 4.4, 4.10, 5.3, 6.4, 7.10, 8.5 | in-task (4.4, 4.10, 5.3, 6.4, 7.10, 8.5) | 7.5, 9.6 |
| FR-3.4.7 | 7.9, 7.10, 8.5 | in-task (7.9, 7.10, 8.5) | 7.4, 7.5, 9.5, 9.6 |
| FR-3.4.8 | 2.1, 3.4, 3.5, 4.4, 4.11, 5.3, 6.4, 7.9, 8.5 | in-task (2.1, 3.4, 3.5, 4.4, 4.11, 5.3, 6.4, 7.9, 8.5) | 7.4, 9.5 |
| FR-3.5.1 | 3.12, 8.5 | in-task (3.12, 8.5) | 9.7 |
| FR-3.5.2 | 3.12 | in-task (3.12) | 9.7 |
| FR-3.5.3 | 3.12, 8.5 | in-task (3.12, 8.5) | 9.7 |
| FR-3.5.4 | 3.12 | in-task (3.12) | 9.7 |
| FR-3.5.5 | 8.5 | in-task (8.5) | 9.7 |
| FR-3.6.1 | 5.6, 8.3 | in-task (5.6, 8.3) | 9.7 |
| FR-3.6.2 | **— (deliberate gap)** | — | — |
| FR-3.6.3 | **— (deliberate gap, out of PoC scope)** | — | — |
| FR-3.7.1 | 1.2, 1.4 | in-task (1.2, 1.4) | 10.1 |
| FR-3.7.2 | 3.17, 8.3 | in-task (3.17, 8.3) | 9.2 |
| FR-3.7.3 | 3.17, 8.3 | in-task (3.17, 8.3) | 9.2 |
| NFR-6.1 | 2.3, 2.8, 3.1, 3.6, 3.10, 4.12, 8.5 | in-task (2.3, 2.8, 3.1, 3.6, 3.10, 4.12, 8.5) | 7.2, 7.6 |
| NFR-6.2 | 7.9 | in-task (7.9) | 9.5 |
| NFR-6.3 | 2.1, 2.8, 3.5, 3.16, 3.18, 4.2, 4.5, 4.13, 4.14, 6.1, 6.7, 8.2 | in-task (as listed) | 9.7, 10.3 |
| NFR-6.4 | 2.5, 5.1, 6.8, 8.4 | in-task (2.5, 5.1, 6.8, 8.4) | 7.6, 9.7 |
| NFR-6.5 | 1.2, 1.4, 2.2, 3.16, 4.3, 4.6, 4.12, 5.6, 6.5, I.1 | in-task (as listed) | 10.1, 10.3, I.2 |
| NFR-6.6 | 2.2, 4.2, 4.3, 6.5, **I.1** | in-task (2.2, 4.2, 4.3, 6.5, I.1) | **I.2** |
| NFR-6.7 | 2.2, 3.9, 6.1, 6.5, **I.1** | in-task (2.2, 3.9, 6.1, 6.5, I.1) | 7.6, **I.2** |

**Two gaps, stated rather than hidden.** FR-3.6.2 (landing page and install funnel) has no task. It
belongs to `client/`, which the low-level design excludes from its scope in §1 — this plan decomposes
that design and inherits the boundary. FR-3.6.3 (dashboard) has no task either, and for a different
reason: it is the only requirement that forces `externally_connectable` into the manifest, which
widens the extension's attack surface and its Web Store permission warnings for a surface nothing in
the PoC demo touches. It is deliberately deferred, not overlooked — see the decisions record, and see
Task 5.6's developer note for exactly what reinstating it would require. Neither requirement is
withdrawn and neither is satisfied; both are unplanned, and Task 10.2's citation sweep carries them
as its **two** allowlisted exemptions so that the sweep passes without either gap quietly
disappearing. Anything else missing from this table is a bug in the plan.

**The manual gate is not in the table, and that is on purpose.** Task 8.6 walks FR-3.1.1, FR-3.3.x,
FR-3.4.x, FR-3.5.x and FR-3.7.2/3 by hand in a real browser, but it is a gate rather than a test:
its output is `docs/acceptance.md` and a human's judgement, not an assertion a CI run can re-check.
Listing it as an integration test for two dozen requirements would suggest a coverage it does not
provide. It is in the tracker and in the batch sequence; it is not evidence in this table.

**Requirements-document sections, not FR IDs.** Several tasks cite `§4.1` (the endpoint table and
the `X-Boomerang-Client-Version` header), `§4.2` (the error shape and its closed reason table) or
`§5.1`/`§5.2` (configuration, including `MIN_CLIENT_VERSION`, `MAX_INGEST_BYTES` and
`API_REQUEST_TIMEOUT_MS`). These are normative but carry no FR ID, so they cannot appear as rows
above. Tasks 2.1, 2.5, 3.1, 3.6, 3.8, 3.18, 4.13, 6.5 and 7.6 are the ones that hold them; Task 3.18
freezes the wire shapes they describe as files both workspaces assert against, and Task 10.2 sweeps
their citations — and, since the second revision, their configuration-parameter names — alongside the
FR ones.

---

## Plan Summary

| Batch | Tasks | Tracks | Theme |
|-------|-------|--------|-------|
| 0 | 3 | 3 | De-risking — the retailer flow, USPS access, and Bedrock latency, before anything is built on them |
| 1 | 5 | 2 | Scaffolding — both workspaces exist, CI runs, the extension IDs are pinned, coverage is enforced |
| 2 | 8 | 7 | Foundations — errors, config, logging, shared types, and the test fakes |
| 3 | 18 | 11 | Leaf modules — wire models, carrier protocol, extraction, ranking, validation, and the frozen contracts |
| 4 | 14 | 6 | Adapters and stores — Bedrock, USPS, the mock carrier, and the whole storage layer |
| 5 | 6 | 5 | Services — the three server services and the driver's collaborators |
| 6 | 8 | 2 | Assembly — routes and app wiring; the return state machine |
| — | 3 | 1 | **Deployment track** — the Lambda topology, a live smoke test, and USPS sandbox reconciliation |
| 7 | 10 | 3 | Server integration tests, and the return flows end to end in the worker |
| 8 | 6 | 3 | Entrypoints — content script, background worker, popup surfaces, and the manual acceptance gate |
| 9 | 7 | 2 | Extension integration tests across all six §8.3 row groups |
| 10 | 3 | 3 | CI enforcement — bundle posture, citation sweep, module boundaries |
| **Total** | **91** | | |

**What "done" means.** After Batch 10, the checks that keep this architecture honest run in CI rather
than in review attention: the shipped manifest declares only `activeTab`, `scripting` and `storage`,
carries the **prod** pinned key, and has no `externally_connectable` (Task 10.1); `routes` cannot
import `carriers` or `bedrock`, and `services` cannot import `fastapi` (Task 10.3); the wire shapes
in `contracts/` fail exactly one workspace's suite when either side drifts (Task 3.18); and every
requirement except the two declared gaps — FR-3.6.2 and FR-3.6.3 — has a task citing it, as does every
configuration parameter named in §5.1 and §5.2 (Task 10.2). What CI cannot check, Task 8.6 checks by
hand once, and records in `docs/acceptance.md`.
