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

**The graphs live in the design, and only there.**
[`design/boomerang-low-level-design.md`](../design/boomerang-low-level-design.md) §2.1 draws the
server's module graph and §2.2 draws the extension's. Those two are authoritative and this plan
keeps no copy of either. A copy drifts, and the extension graph is the kind that drifts silently:
most of what it says lives in the qualifiers on its edges — `POPUP -- "reads only" --> STORE` *is*
the single-writer rule — and in a completeness claim that only holds if every edge and both
platform nodes are actually drawn. A paraphrase that keeps the boxes and drops the labels still
looks right while permitting what the design forbids. Task 10.3 encodes both graphs as lint
contracts and is told to read §2.1 and §2.2 directly, for the same reason.

**The two graphs are not the same kind of document, and the difference is load-bearing.** §2.1
draws the server's *layering rule* rather than every edge — `main` and `prompts` sit outside the
layering and are omitted because of that, not because importing them is forbidden. §2.2 is
**complete and prohibitive**: an edge that is not drawn is not permitted, an edge carrying a
qualifier is permitted only for what the qualifier says, and `src/types/` and `src/config.ts` are
the two named exemptions. Read §2.1 for the invariant; read §2.2 for the whole permitted set.

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

- [Task 0.1: Walk the retailer return flow by hand and record what is there](tasks/batch-00/0.01-walk-the-retailer-return-flow-by-hand-and-record.md) — prerequisites: none · conflicts: none

---

### Track B: USPS access [external]

- [Task 0.2: File the USPS API access request](tasks/batch-00/0.02-file-the-usps-api-access-request.md) — prerequisites: none · conflicts: none

---

### Track C: Model latency [measurement]

- [Task 0.3: Measure Bedrock parse and action latency](tasks/batch-00/0.03-measure-bedrock-parse-and-action-latency.md) — prerequisites: 0.1 · conflicts: none

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

- [Task 1.1: Reconcile the existing server test harness with the §8 layout](tasks/batch-01/1.01-reconcile-the-existing-server-test-harness-with.md) — prerequisites: none · conflicts: none

---

### Track B: Extension workspace [extension]

- [Task 1.2: WXT project scaffold and MV3 manifest](tasks/batch-01/1.02-wxt-project-scaffold-and-mv3-manifest.md) — prerequisites: none · conflicts: 1.4
- [Task 1.4: Generate and pin the extension keypairs](tasks/batch-01/1.04-generate-and-pin-the-extension-keypairs.md) — prerequisites: 1.2 · conflicts: 1.2

---

### Track C: Repository CI [repo]

- [Task 1.3: Continuous integration for both workspaces](tasks/batch-01/1.03-continuous-integration-for-both-workspaces.md) — prerequisites: none · conflicts: none

---

### Track D: Extension quality gates [extension]

- [Task 1.5: Extension coverage floor and pre-commit hook](tasks/batch-01/1.05-extension-coverage-floor-and-pre-commit-hook.md) — prerequisites: 1.2 · conflicts: none

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

- [Task 2.1: `app/errors.py` — the exception hierarchy](tasks/batch-02/2.01-app-errors-py-the-exception-hierarchy.md) — prerequisites: 1.1 · conflicts: none

---

### Track B: Server configuration [server]

- [Task 2.2: `app/config.py` — `Settings` and fail-fast validation](tasks/batch-02/2.02-app-config-py-settings-and-fail-fast-validation.md) — prerequisites: 1.1 · conflicts: none

---

### Track C: Server logging [server]

- [Task 2.3: `app/logging.py` — redacting formatter and request-id binding](tasks/batch-02/2.03-app-logging-py-redacting-formatter-and-request-id.md) — prerequisites: 1.1 · conflicts: none

---

### Track D: Extension shared vocabulary [extension]

- [Task 2.4: `src/types/` — entities, session, and the state enums](tasks/batch-02/2.04-src-types-entities-session-and-the-state-enums.md) — prerequisites: 1.2 · conflicts: none

---

### Track E: Extension build-time config [extension]

- [Task 2.5: `src/config.ts` — build-time constants](tasks/batch-02/2.05-src-config-ts-build-time-constants.md) — prerequisites: 1.2 · conflicts: none

---

### Track F: Extension fake browser [extension]

- [Task 2.6: Fake `chrome.storage.local`](tasks/batch-02/2.06-fake-chrome-storage-local.md) — prerequisites: 1.2 · conflicts: 2.7
- [Task 2.7: Fake `tabs`, `scripting`, `permissions`, worker lifecycle, and clock](tasks/batch-02/2.07-fake-tabs-scripting-permissions-worker-lifecycle.md) — prerequisites: 2.6 · conflicts: 2.6

---

### Track G: Extension DOM fixtures [extension]

- [Task 2.8: Retailer DOM fixture harness](tasks/batch-02/2.08-retailer-dom-fixture-harness.md) — prerequisites: 0.1, 1.2 · conflicts: none

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

- [Task 3.1: `app/models/common.py` — strict base model and the error body](tasks/batch-03/3.01-app-models-common-py-strict-base-model-and-the.md) — prerequisites: 2.1 · conflicts: 3.2, 3.3, 3.4
- [Task 3.2: `app/models/orders.py` — ingestion payloads](tasks/batch-03/3.02-app-models-orders-py-ingestion-payloads.md) — prerequisites: 3.1 · conflicts: 3.1, 3.3, 3.4
- [Task 3.3: `app/models/returns.py` — `ActionKind` and `ProposedAction`](tasks/batch-03/3.03-app-models-returns-py-actionkind-and.md) — prerequisites: 3.1 · conflicts: 3.1, 3.2, 3.4
- [Task 3.4: `app/models/pickups.py` — address, eligibility, schedule, refresh, cancel](tasks/batch-03/3.04-app-models-pickups-py-address-eligibility.md) — prerequisites: 3.1 · conflicts: 3.1, 3.2, 3.3
- [Task 3.5: `app/carriers/base.py` — the `CarrierAdapter` protocol](tasks/batch-03/3.05-app-carriers-base-py-the-carrieradapter-protocol.md) — prerequisites: 3.4 · conflicts: none

---

### Track B: Server middleware [server]

- [Task 3.6: `app/middleware.py` — request id](tasks/batch-03/3.06-app-middleware-py-request-id.md) — prerequisites: 2.3 · conflicts: none

---

### Track C: Server dependencies and version gate [server]

- [Task 3.8: `app/deps.py` — app-state accessors and the `X-Boomerang-Client-Version` gate](tasks/batch-03/3.08-app-deps-py-app-state-accessors-and-the-x.md) — prerequisites: 2.1, 2.2 · conflicts: none

---

### Track I: Server window derivation [server]

- [Task 3.7: `app/services/window.py` — return-window derivation and urgency](tasks/batch-03/3.07-app-services-window-py-return-window-derivation.md) — prerequisites: 3.2 · conflicts: none

---

### Track D: Extension extraction and egress scan [extension]

- [Task 3.9: `src/extract/` — subtree selection and sanitisation](tasks/batch-03/3.09-src-extract-subtree-selection-and-sanitisation.md) — prerequisites: 2.4, 2.5, 2.8 · conflicts: 3.10
- [Task 3.10: `src/extract/` — the fail-closed egress scan](tasks/batch-03/3.10-src-extract-the-fail-closed-egress-scan.md) — prerequisites: 3.9 · conflicts: 3.9

---

### Track E: Extension ranking [extension]

- [Task 3.11: `src/ranking/` — urgency ordering](tasks/batch-03/3.11-src-ranking-urgency-ordering.md) — prerequisites: 2.4 · conflicts: none

---

### Track F: Extension calendar [extension]

- [Task 3.12: `src/calendar/` — template URL and `.ics`](tasks/batch-03/3.12-src-calendar-template-url-and-ics.md) — prerequisites: 2.4, 2.5 · conflicts: none

---

### Track G: Extension retailer adapters [extension]

- [Task 3.13: `src/adapters/` — adapter type and registry](tasks/batch-03/3.13-src-adapters-adapter-type-and-registry.md) — prerequisites: 2.4 · conflicts: 3.14
- [Task 3.14: The PoC retailer adapter](tasks/batch-03/3.14-the-poc-retailer-adapter.md) — prerequisites: 0.1, 2.8, 3.13 · conflicts: 3.13

---

### Track J: Extension validation [extension]

- [Task 3.15: `src/validation/` — the action validator](tasks/batch-03/3.15-src-validation-the-action-validator.md) — prerequisites: 2.4, 3.13 · conflicts: 3.16
- [Task 3.16: `src/validation/` — the order response validator](tasks/batch-03/3.16-src-validation-the-order-response-validator.md) — prerequisites: 2.4 · conflicts: 3.15

---

### Track H: Extension permissions [extension]

- [Task 3.17: `src/permissions/` — two-tier permission state](tasks/batch-03/3.17-src-permissions-two-tier-permission-state.md) — prerequisites: 2.4, 2.7 · conflicts: none

---

### Track K: Wire contract fixtures [repo]

- [Task 3.18: `contracts/` — golden payloads both sides assert against](tasks/batch-03/3.18-contracts-golden-payloads-both-sides-assert.md) — prerequisites: 3.4, 3.16 · conflicts: none

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

- [Task 4.2: `app/bedrock.py` — settings-driven client and per-call-site models](tasks/batch-04/4.02-app-bedrock-py-settings-driven-client-and-per.md) — prerequisites: 2.2 · conflicts: none
- [Task 4.1: `app/prompts/` — tool schemas generated from the enums](tasks/batch-04/4.01-app-prompts-tool-schemas-generated-from-the-enums.md) — prerequisites: 3.2, 3.3, 4.2 · conflicts: none

---

### Track B: Server USPS carrier [server]

- [Task 4.3: `app/carriers/usps/token.py` — OAuth token provider](tasks/batch-04/4.03-app-carriers-usps-token-py-oauth-token-provider.md) — prerequisites: 2.1, 2.2 · conflicts: 4.4, 4.5
- [Task 4.4: `app/carriers/usps/adapter.py` — `UspsAdapter`](tasks/batch-04/4.04-app-carriers-usps-adapter-py-uspsadapter.md) — prerequisites: 3.4, 3.5, 4.3 · conflicts: 4.3, 4.5
- [Task 4.5: `app/carriers/usps/scripted.py` — `ScriptedUspsAdapter` (test double)](tasks/batch-04/4.05-app-carriers-usps-scripted-py-scripteduspsadapter.md) — prerequisites: 3.4, 3.5 · conflicts: 4.3, 4.4

---

### Track E: Server runtime mock carrier [server]

- [Task 4.14: `app/carriers/mock.py` — `MockCarrierAdapter` (runtime stub)](tasks/batch-04/4.14-app-carriers-mock-py-mockcarrieradapter-runtime.md) — prerequisites: 3.4, 3.5, 3.18 · conflicts: none

---

### Track C: Extension storage [extension]

- [Task 4.6: `src/storage/` — key layout, defensive read, rebuild, and the barrel](tasks/batch-04/4.06-src-storage-key-layout-defensive-read-rebuild-and.md) — prerequisites: 2.4, 2.6 · conflicts: 4.7
- [Task 4.7: `StorageCoordinator.transact` — the serialising queue](tasks/batch-04/4.07-storagecoordinator-transact-the-serialising-queue.md) — prerequisites: 4.6 · conflicts: 4.6, 4.12
- [Task 4.8: `OrderRepository`](tasks/batch-04/4.08-orderrepository.md) — prerequisites: 4.7 · conflicts: none
- [Task 4.9: `ReturnRepository`](tasks/batch-04/4.09-returnrepository.md) — prerequisites: 4.7 · conflicts: none
- [Task 4.10: `PickupRepository`](tasks/batch-04/4.10-pickuprepository.md) — prerequisites: 4.7 · conflicts: none
- [Task 4.11: `AddressRepository` and `SessionStore`](tasks/batch-04/4.11-addressrepository-and-sessionstore.md) — prerequisites: 4.7 · conflicts: none
- [Task 4.12: Coordinator cross-entity operations — eviction and clear-all](tasks/batch-04/4.12-coordinator-cross-entity-operations-eviction-and.md) — prerequisites: 4.8, 4.9, 4.10, 4.11 · conflicts: 4.7

---

### Track D: Extension server client [extension]

- [Task 4.13: `src/api/` — the typed server client](tasks/batch-04/4.13-src-api-the-typed-server-client.md) — prerequisites: 2.5, 3.15, 3.16, 3.18 · conflicts: none

---

### Batch 4 Commit Checkpoint

After all tracks complete:
- [ ] Server tests pass: `cd server && uv run pytest`
- [ ] Extension tests pass: `cd extension && bunx tsc --noEmit && bun run test`
- [ ] The server can talk to Bedrock with forced tool choice and to USPS with a cached token, and has
      a scriptable carrier double for integration tests.
- [ ] The extension has its whole persistence layer, including eviction that protects live returns and
      unsettled pickups, and a server client that refuses to retry a booking.
- [ ] `tests/storage/single-set-law.test.ts` holds its first four rows (`PickupRepository.save_intent`,
      `.promote`, `clear_all`, eviction's order+return delete) — created in Task 4.10, completed by
      Task 4.12. The remaining two land in Batches 6 and 7.

---

## Batch 5: Services and Driver Collaborators

### Track A: Server ingest service [server]

- [Task 5.1: `app/services/ingest.py` — `IngestService`](tasks/batch-05/5.01-app-services-ingest-py-ingestservice.md) — prerequisites: 2.1, 3.2, 3.7, 4.1, 4.2 · conflicts: none

---

### Track B: Server action service [server]

- [Task 5.2: `app/services/action.py` — `ActionService`](tasks/batch-05/5.02-app-services-action-py-actionservice.md) — prerequisites: 2.1, 3.3, 4.1, 4.2 · conflicts: none

---

### Track C: Server pickup service [server]

- [Task 5.3: `app/services/pickup.py` — `PickupService`](tasks/batch-05/5.03-app-services-pickup-py-pickupservice.md) — prerequisites: 2.1, 3.4, 3.5 · conflicts: none

---

### Track D: Extension driver collaborators [extension]

- [Task 5.4: `TabHandle`, `TabHandleFactory`, and `UserPrompt`](tasks/batch-05/5.04-tabhandle-tabhandlefactory-and-userprompt.md) — prerequisites: 2.4, 2.7 · conflicts: 5.5
- [Task 5.5: `StepExecutor`](tasks/batch-05/5.05-stepexecutor.md) — prerequisites: 3.15, 5.4 · conflicts: 5.4

---

### Track E: Extension messaging [extension]

- [Task 5.6: `src/messaging/` — internal message routing](tasks/batch-05/5.06-src-messaging-internal-message-routing.md) — prerequisites: 2.4, 4.12 · conflicts: none

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

- [Task 6.1: `app/routes/health.py`](tasks/batch-06/6.01-app-routes-health-py.md) — prerequisites: 1.1 · conflicts: 6.2, 6.3, 6.4
- [Task 6.2: `app/routes/orders.py` — `POST /orders/ingest`](tasks/batch-06/6.02-app-routes-orders-py-post-orders-ingest.md) — prerequisites: 3.8, 5.1, 6.1 · conflicts: 6.1, 6.3, 6.4
- [Task 6.3: `app/routes/returns.py` — `POST /returns/next-step`](tasks/batch-06/6.03-app-routes-returns-py-post-returns-next-step.md) — prerequisites: 3.8, 5.2, 6.2 · conflicts: 6.1, 6.2, 6.4
- [Task 6.4: `app/routes/pickups.py` — the four pickup endpoints](tasks/batch-06/6.04-app-routes-pickups-py-the-four-pickup-endpoints.md) — prerequisites: 3.8, 5.3, 6.3 · conflicts: 6.1, 6.2, 6.3
- [Task 6.5: `app/main.py` — lifespan, handlers, CORS, adapter selection, Mangum](tasks/batch-06/6.05-app-main-py-lifespan-handlers-cors-adapter.md) — prerequisites: 2.2, 3.6, 4.2, 4.4, 4.14, 6.1, 6.2, 6.3, 6.4 · conflicts: none

---

### Track B: Extension driver core [extension]

- [Task 6.6: `ReturnDriver` — construction, `transition`, and `start`](tasks/batch-06/6.06-returndriver-construction-transition-and-start.md) — prerequisites: 4.9, 4.10, 4.11, 5.4, 5.5 · conflicts: 6.7, 6.8
- [Task 6.7: State machine edges and rehydration](tasks/batch-06/6.07-state-machine-edges-and-rehydration.md) — prerequisites: 6.6 · conflicts: 6.6, 6.8
- [Task 6.8: Selector-first step loop and the model fallback](tasks/batch-06/6.08-selector-first-step-loop-and-the-model-fallback.md) — prerequisites: 3.10, 4.13, 5.5, 6.7 · conflicts: 6.6, 6.7

---

### Batch 6 Commit Checkpoint

After all tracks complete:
- [ ] Server tests pass and the app starts: `cd server && uv run pytest && uv run fastapi dev app/main.py`
- [ ] Extension tests pass: `cd extension && bunx tsc --noEmit && bun run test`
- [ ] All seven endpoints are served, version-gated, and render one error shape.
- [ ] The driver drives a return with selectors, falls back to the model only when it must, and
      survives a worker death by rehydrating from storage.
- [ ] `tests/storage/single-set-law.test.ts` holds its fifth row (`ReturnDriver.transition`, Task
      6.6). The last lands in Batch 7.

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

- [Task I.1: Replace the Terraform with the Lambda topology](tasks/deployment/I.1-replace-the-terraform-with-the-lambda-topology.md) — prerequisites: 1.4, 6.5 · conflicts: none
- [Task I.2: First deploy and a live smoke test](tasks/deployment/I.2-first-deploy-and-a-live-smoke-test.md) — prerequisites: I.1 · conflicts: none
- [Task I.3: Reconcile `UspsAdapter` against the USPS sandbox](tasks/deployment/I.3-reconcile-uspsadapter-against-the-usps-sandbox.md) — prerequisites: 0.2, 4.4, I.1 · conflicts: none

---

## Batch 7: Server Integration Tests; Driver Flows

### Track A: Server integration harness [server]

- [Task 7.1: Integration test harness](tasks/batch-07/7.01-integration-test-harness.md) — prerequisites: 4.5, 6.5 · conflicts: none

---

### Track B: Server integration rows [server]

- [Task 7.2: Ingestion integration rows](tasks/batch-07/7.02-ingestion-integration-rows.md) — prerequisites: 7.1 · conflicts: none
- [Task 7.3: Next-step integration rows](tasks/batch-07/7.03-next-step-integration-rows.md) — prerequisites: 7.1 · conflicts: none
- [Task 7.4: Eligibility and schedule integration rows](tasks/batch-07/7.04-eligibility-and-schedule-integration-rows.md) — prerequisites: 7.1 · conflicts: none
- [Task 7.5: Refresh and cancel integration rows](tasks/batch-07/7.05-refresh-and-cancel-integration-rows.md) — prerequisites: 7.1 · conflicts: none
- [Task 7.6: Cross-cutting integration rows](tasks/batch-07/7.06-cross-cutting-integration-rows.md) — prerequisites: 7.1 · conflicts: none

---

### Track C: Extension driver flows [extension]

- [Task 7.7: The return-method choice flow](tasks/batch-07/7.07-the-return-method-choice-flow.md) — prerequisites: 3.14, 6.8 · conflicts: 7.8, 7.9, 7.10
- [Task 7.8: `derive_label_carrier` — three sources, in order](tasks/batch-07/7.08-derive-label-carrier-three-sources-in-order.md) — prerequisites: 7.7 · conflicts: 7.7, 7.9, 7.10
- [Task 7.9: Print affirmation, pickup offer, and consent](tasks/batch-07/7.09-print-affirmation-pickup-offer-and-consent.md) — prerequisites: 4.10, 4.13, 7.8 · conflicts: 7.7, 7.8, 7.10
- [Task 7.10: Cancellation orchestration](tasks/batch-07/7.10-cancellation-orchestration.md) — prerequisites: 7.9 · conflicts: 7.7, 7.8, 7.9

---

### Batch 7 Commit Checkpoint

After all tracks complete:
- [ ] Server unit and integration tests pass: `cd server && uv run pytest`
- [ ] Extension tests pass: `cd extension && bunx tsc --noEmit && bun run test`
- [ ] **The server is functionally complete** — every §8.3 server row is green.
- [ ] The extension's return flow is complete from scan to printed label to booked pickup to
      cancellation, all unit-tested against the fake browser.
- [ ] `tests/storage/single-set-law.test.ts` is complete: all six rows present (Tasks 4.10, 4.12,
      6.6, 7.10), each asserting its write is exactly one `set` call.

---

## Batch 8: Entrypoints and Wiring

### Track A: Content script and service worker [extension]

- [Task 8.1: `entrypoints/content.ts`](tasks/batch-08/8.01-entrypoints-content-ts.md) — prerequisites: 3.9, 3.13, 5.6 · conflicts: none
- [Task 8.2: `entrypoints/background.ts` — the worker wiring graph](tasks/batch-08/8.02-entrypoints-background-ts-the-worker-wiring-graph.md) — prerequisites: 3.17, 4.12, 5.6, 7.10, 8.1 · conflicts: none

---

### Track B: Popup surfaces [extension]

- [Task 8.3: Popup shell, ranked list, scan gesture, permission offer](tasks/batch-08/8.03-popup-shell-ranked-list-scan-gesture-permission.md) — prerequisites: 3.11, 3.17, 8.2 · conflicts: 8.4, 8.5
- [Task 8.4: Popup return surfaces — choice, affirmation, stuck](tasks/batch-08/8.04-popup-return-surfaces-choice-affirmation-stuck.md) — prerequisites: 8.3 · conflicts: 8.3, 8.5
- [Task 8.5: Popup pickup, calendar, clear-all, and the simulated-booking marker](tasks/batch-08/8.05-popup-pickup-calendar-clear-all-and-the-simulated.md) — prerequisites: 3.12, 4.12, 8.4 · conflicts: 8.3, 8.4

---

### Gate: Manual acceptance [extension]

- [Task 8.6: Walk the whole product by hand in a real browser](tasks/batch-08/8.06-walk-the-whole-product-by-hand-in-a-real-browser.md) — prerequisites: 8.5 · conflicts: none

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
- [ ] The order cap is enforced end-to-end: ingesting past `MAX_STORED_ORDERS` evicts down to the cap
      via `evict_if_over_cap()` (Task 8.2), the only call site routine ingestion has for it.

---

## Batch 9: Extension Integration Tests

### Track A: Harness [extension]

- [Task 9.1: End-to-end extension test harness](tasks/batch-09/9.01-end-to-end-extension-test-harness.md) — prerequisites: 8.6 · conflicts: none

---

### Track B: Integration rows [extension]

- [Task 9.2: Ingestion and permission rows](tasks/batch-09/9.02-ingestion-and-permission-rows.md) — prerequisites: 9.1 · conflicts: none
- [Task 9.3: Driving rows](tasks/batch-09/9.03-driving-rows.md) — prerequisites: 9.1 · conflicts: none
- [Task 9.4: State machine and terminal rows](tasks/batch-09/9.04-state-machine-and-terminal-rows.md) — prerequisites: 9.1 · conflicts: none
- [Task 9.5: Pickup rows](tasks/batch-09/9.05-pickup-rows.md) — prerequisites: 9.1 · conflicts: none
- [Task 9.6: Cancellation rows](tasks/batch-09/9.06-cancellation-rows.md) — prerequisites: 9.1 · conflicts: none
- [Task 9.7: Platform rows](tasks/batch-09/9.07-platform-rows.md) — prerequisites: 9.1 · conflicts: none

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

- [Task 10.1: Prod-bundle assertion in CI](tasks/batch-10/10.01-prod-bundle-assertion-in-ci.md) — prerequisites: 1.4, 8.5 · conflicts: none

---

### Track B: Citation sweep

- [Task 10.2: Requirement and configuration citation sweep](tasks/batch-10/10.02-requirement-and-configuration-citation-sweep.md) — prerequisites: 7.6, 9.7 · conflicts: none

---

### Track C: Import boundary enforcement

- [Task 10.3: Enforce the module dependency graphs](tasks/batch-10/10.03-enforce-the-module-dependency-graphs.md) — prerequisites: 6.5, 8.5 · conflicts: none

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

| Task | Description | Prerequisites | Conflicts | Parallel with | Status |
|------|-------------|---------------|-----------|---------------|--------|
| [0.1](tasks/batch-00/0.01-walk-the-retailer-return-flow-by-hand-and-record.md) | Walk the retailer return flow by hand and record what is there | None | None | 0.2 | [ ] |
| [0.2](tasks/batch-00/0.02-file-the-usps-api-access-request.md) | File the USPS API access request | None | None | 0.1 | [ ] |
| [0.3](tasks/batch-00/0.03-measure-bedrock-parse-and-action-latency.md) | Measure Bedrock parse and action latency | 0.1 | None | None | [ ] |
| [1.1](tasks/batch-01/1.01-reconcile-the-existing-server-test-harness-with.md) | Reconcile the existing server test harness with the §8 layout | None | None | 1.2 | [ ] |
| [1.2](tasks/batch-01/1.02-wxt-project-scaffold-and-mv3-manifest.md) | WXT project scaffold and MV3 manifest | None | 1.4 | 1.1 | [ ] |
| [1.3](tasks/batch-01/1.03-continuous-integration-for-both-workspaces.md) | Continuous integration for both workspaces | None | None | 1.1, 1.2 | [ ] |
| [1.4](tasks/batch-01/1.04-generate-and-pin-the-extension-keypairs.md) | Generate and pin the extension keypairs | 1.2 | 1.2 | 1.1, 1.3 | [ ] |
| [1.5](tasks/batch-01/1.05-extension-coverage-floor-and-pre-commit-hook.md) | Extension coverage floor and pre-commit hook | 1.2 | None | 1.1, 1.3, 1.4 | [ ] |
| [2.1](tasks/batch-02/2.01-app-errors-py-the-exception-hierarchy.md) | `app/errors.py` — the exception hierarchy | 1.1 | None | 2.2–2.8 | [ ] |
| [2.2](tasks/batch-02/2.02-app-config-py-settings-and-fail-fast-validation.md) | `app/config.py` — `Settings` and fail-fast validation | 1.1 | None | 2.1, 2.3–2.8 | [ ] |
| [2.3](tasks/batch-02/2.03-app-logging-py-redacting-formatter-and-request-id.md) | `app/logging.py` — redacting formatter and request-id binding | 1.1 | None | 2.1, 2.2, 2.4–2.8 | [ ] |
| [2.4](tasks/batch-02/2.04-src-types-entities-session-and-the-state-enums.md) | `src/types/` — entities, session, and the state enums | 1.2 | None | 2.1–2.3, 2.5–2.8 | [ ] |
| [2.5](tasks/batch-02/2.05-src-config-ts-build-time-constants.md) | `src/config.ts` — build-time constants | 1.2 | None | 2.1–2.4, 2.6–2.8 | [ ] |
| [2.6](tasks/batch-02/2.06-fake-chrome-storage-local.md) | Fake `chrome.storage.local` | 1.2 | 2.7 | 2.1–2.5, 2.8 | [ ] |
| [2.7](tasks/batch-02/2.07-fake-tabs-scripting-permissions-worker-lifecycle.md) | Fake `tabs`, `scripting`, `permissions`, worker lifecycle, and clock | 2.6 | 2.6 | 2.1–2.5, 2.8 | [ ] |
| [2.8](tasks/batch-02/2.08-retailer-dom-fixture-harness.md) | Retailer DOM fixture harness | 0.1, 1.2 | None | 2.1–2.7 | [ ] |
| [3.1](tasks/batch-03/3.01-app-models-common-py-strict-base-model-and-the.md) | `app/models/common.py` — strict base model and the error body | 2.1 | 3.2, 3.3, 3.4 | 3.6, 3.8–3.17 | [ ] |
| [3.2](tasks/batch-03/3.02-app-models-orders-py-ingestion-payloads.md) | `app/models/orders.py` — ingestion payloads | 3.1 | 3.1, 3.3, 3.4 | 3.6, 3.8–3.17 | [ ] |
| [3.3](tasks/batch-03/3.03-app-models-returns-py-actionkind-and.md) | `app/models/returns.py` — `ActionKind` and `ProposedAction` | 3.1 | 3.1, 3.2, 3.4 | 3.6, 3.8–3.17 | [ ] |
| [3.4](tasks/batch-03/3.04-app-models-pickups-py-address-eligibility.md) | `app/models/pickups.py` — address, eligibility, schedule, refresh, cancel | 3.1 | 3.1, 3.2, 3.3 | 3.6, 3.8–3.17 | [ ] |
| [3.5](tasks/batch-03/3.05-app-carriers-base-py-the-carrieradapter-protocol.md) | `app/carriers/base.py` — the `CarrierAdapter` protocol | 3.4 | None | 3.6, 3.8–3.17 | [ ] |
| [3.6](tasks/batch-03/3.06-app-middleware-py-request-id.md) | `app/middleware.py` — request id | 2.3 | None | 3.1–3.5, 3.8–3.17 | [ ] |
| [3.7](tasks/batch-03/3.07-app-services-window-py-return-window-derivation.md) | `app/services/window.py` — return-window derivation and urgency | 3.2 | None | 3.6, 3.8–3.17 | [ ] |
| [3.8](tasks/batch-03/3.08-app-deps-py-app-state-accessors-and-the-x.md) | `app/deps.py` — app-state accessors and the `X-Boomerang-Client-Version` gate | 2.1, 2.2 | None | 3.1–3.6, 3.9–3.17 | [ ] |
| [3.9](tasks/batch-03/3.09-src-extract-subtree-selection-and-sanitisation.md) | `src/extract/` — subtree selection and sanitisation | 2.4, 2.5, 2.8 | 3.10 | 3.1–3.8, 3.11–3.17 | [ ] |
| [3.10](tasks/batch-03/3.10-src-extract-the-fail-closed-egress-scan.md) | `src/extract/` — the fail-closed egress scan | 3.9 | 3.9 | 3.1–3.8, 3.11–3.17 | [ ] |
| [3.11](tasks/batch-03/3.11-src-ranking-urgency-ordering.md) | `src/ranking/` — urgency ordering | 2.4 | None | 3.1–3.10, 3.12–3.17 | [ ] |
| [3.12](tasks/batch-03/3.12-src-calendar-template-url-and-ics.md) | `src/calendar/` — template URL and `.ics` | 2.4, 2.5 | None | 3.1–3.11, 3.13–3.17 | [ ] |
| [3.13](tasks/batch-03/3.13-src-adapters-adapter-type-and-registry.md) | `src/adapters/` — adapter type and registry | 2.4 | 3.14 | 3.1–3.12, 3.15–3.17 | [ ] |
| [3.14](tasks/batch-03/3.14-the-poc-retailer-adapter.md) | The PoC retailer adapter | 0.1, 2.8, 3.13 | 3.13 | 3.1–3.12, 3.15–3.17 | [ ] |
| [3.15](tasks/batch-03/3.15-src-validation-the-action-validator.md) | `src/validation/` — the action validator | 2.4, 3.13 | 3.16 | 3.1–3.12, 3.17 | [ ] |
| [3.16](tasks/batch-03/3.16-src-validation-the-order-response-validator.md) | `src/validation/` — the order response validator | 2.4 | 3.15 | 3.1–3.12, 3.17 | [ ] |
| [3.17](tasks/batch-03/3.17-src-permissions-two-tier-permission-state.md) | `src/permissions/` — two-tier permission state | 2.4, 2.7 | None | 3.1–3.16 | [ ] |
| [3.18](tasks/batch-03/3.18-contracts-golden-payloads-both-sides-assert.md) | `contracts/` — golden payloads both sides assert against | 3.4, 3.16 | None | 3.6–3.17 | [ ] |
| [4.1](tasks/batch-04/4.01-app-prompts-tool-schemas-generated-from-the-enums.md) | `app/prompts/` — tool schemas generated from the enums | 3.2, 3.3, 4.2 | None | 4.3–4.13 | [ ] |
| [4.2](tasks/batch-04/4.02-app-bedrock-py-settings-driven-client-and-per.md) | `app/bedrock.py` — settings-driven client and per-call-site models | 2.2 | None | 4.3–4.13 | [ ] |
| [4.3](tasks/batch-04/4.03-app-carriers-usps-token-py-oauth-token-provider.md) | `app/carriers/usps/token.py` — OAuth token provider | 2.1, 2.2 | 4.4, 4.5 | 4.1, 4.2, 4.6–4.13 | [ ] |
| [4.4](tasks/batch-04/4.04-app-carriers-usps-adapter-py-uspsadapter.md) | `app/carriers/usps/adapter.py` — `UspsAdapter` | 3.4, 3.5, 4.3 | 4.3, 4.5 | 4.1, 4.2, 4.6–4.13 | [ ] |
| [4.5](tasks/batch-04/4.05-app-carriers-usps-scripted-py-scripteduspsadapter.md) | `app/carriers/usps/scripted.py` — `ScriptedUspsAdapter` (test double) | 3.4, 3.5 | 4.3, 4.4 | 4.1, 4.2, 4.6–4.14 | [ ] |
| [4.6](tasks/batch-04/4.06-src-storage-key-layout-defensive-read-rebuild-and.md) | `src/storage/` — key layout, defensive read, rebuild, and the barrel | 2.4, 2.6 | 4.7 | 4.13 | [ ] |
| [4.7](tasks/batch-04/4.07-storagecoordinator-transact-the-serialising-queue.md) | `StorageCoordinator.transact` — the serialising queue | 4.6 | 4.6, 4.12 | 4.13 | [ ] |
| [4.8](tasks/batch-04/4.08-orderrepository.md) | `OrderRepository` | 4.7 | None | 4.9–4.11, 4.13 | [ ] |
| [4.9](tasks/batch-04/4.09-returnrepository.md) | `ReturnRepository` | 4.7 | None | 4.8, 4.10, 4.11, 4.13 | [ ] |
| [4.10](tasks/batch-04/4.10-pickuprepository.md) | `PickupRepository` | 4.7 | None | 4.8, 4.9, 4.11, 4.13 | [ ] |
| [4.11](tasks/batch-04/4.11-addressrepository-and-sessionstore.md) | `AddressRepository` and `SessionStore` | 4.7 | None | 4.8–4.10, 4.13 | [ ] |
| [4.12](tasks/batch-04/4.12-coordinator-cross-entity-operations-eviction-and.md) | Coordinator cross-entity operations — eviction and clear-all | 4.8, 4.9, 4.10, 4.11 | 4.7 | 4.13 | [ ] |
| [4.13](tasks/batch-04/4.13-src-api-the-typed-server-client.md) | `src/api/` — the typed server client | 2.5, 3.15, 3.16, 3.18 | None | 4.6–4.12, 4.14 | [ ] |
| [4.14](tasks/batch-04/4.14-app-carriers-mock-py-mockcarrieradapter-runtime.md) | `app/carriers/mock.py` — `MockCarrierAdapter` (runtime stub) | 3.4, 3.5, 3.18 | None | 4.1–4.13 | [ ] |
| [5.1](tasks/batch-05/5.01-app-services-ingest-py-ingestservice.md) | `app/services/ingest.py` — `IngestService` | 2.1, 3.2, 3.7, 4.1, 4.2 | None | 5.2–5.6 | [ ] |
| [5.2](tasks/batch-05/5.02-app-services-action-py-actionservice.md) | `app/services/action.py` — `ActionService` | 2.1, 3.3, 4.1, 4.2 | None | 5.1, 5.3–5.6 | [ ] |
| [5.3](tasks/batch-05/5.03-app-services-pickup-py-pickupservice.md) | `app/services/pickup.py` — `PickupService` | 2.1, 3.4, 3.5 | None | 5.1, 5.2, 5.4–5.6 | [ ] |
| [5.4](tasks/batch-05/5.04-tabhandle-tabhandlefactory-and-userprompt.md) | `TabHandle`, `TabHandleFactory`, and `UserPrompt` | 2.4, 2.7 | 5.5 | 5.1–5.3, 5.6 | [ ] |
| [5.5](tasks/batch-05/5.05-stepexecutor.md) | `StepExecutor` | 3.15, 5.4 | 5.4 | 5.1–5.3, 5.6 | [ ] |
| [5.6](tasks/batch-05/5.06-src-messaging-internal-message-routing.md) | `src/messaging/` — internal message routing | 2.4, 4.12 | None | 5.1–5.5 | [ ] |
| [6.1](tasks/batch-06/6.01-app-routes-health-py.md) | `app/routes/health.py` | 1.1 | 6.2, 6.3, 6.4 | 6.6–6.8 | [ ] |
| [6.2](tasks/batch-06/6.02-app-routes-orders-py-post-orders-ingest.md) | `app/routes/orders.py` — `POST /orders/ingest` | 3.8, 5.1, 6.1 | 6.1, 6.3, 6.4 | 6.6–6.8 | [ ] |
| [6.3](tasks/batch-06/6.03-app-routes-returns-py-post-returns-next-step.md) | `app/routes/returns.py` — `POST /returns/next-step` | 3.8, 5.2, 6.2 | 6.1, 6.2, 6.4 | 6.6–6.8 | [ ] |
| [6.4](tasks/batch-06/6.04-app-routes-pickups-py-the-four-pickup-endpoints.md) | `app/routes/pickups.py` — the four pickup endpoints | 3.8, 5.3, 6.3 | 6.1, 6.2, 6.3 | 6.6–6.8 | [ ] |
| [6.5](tasks/batch-06/6.05-app-main-py-lifespan-handlers-cors-adapter.md) | `app/main.py` — lifespan, handlers, CORS, adapter selection, Mangum | 2.2, 3.6, 4.2, 4.4, 4.14, 6.1, 6.2, 6.3, 6.4 | None | 6.6–6.8 | [ ] |
| [6.6](tasks/batch-06/6.06-returndriver-construction-transition-and-start.md) | `ReturnDriver` — construction, `transition`, and `start` | 4.9, 4.10, 4.11, 5.4, 5.5 | 6.7, 6.8 | 6.1–6.5 | [ ] |
| [6.7](tasks/batch-06/6.07-state-machine-edges-and-rehydration.md) | State machine edges and rehydration | 6.6 | 6.6, 6.8 | 6.1–6.5 | [ ] |
| [6.8](tasks/batch-06/6.08-selector-first-step-loop-and-the-model-fallback.md) | Selector-first step loop and the model fallback | 3.10, 4.13, 5.5, 6.7 | 6.6, 6.7 | 6.1–6.5 | [ ] |
| [I.1](tasks/deployment/I.1-replace-the-terraform-with-the-lambda-topology.md) | Replace the Terraform with the Lambda topology | 1.4, 6.5 | None | None | [ ] |
| [I.2](tasks/deployment/I.2-first-deploy-and-a-live-smoke-test.md) | First deploy and a live smoke test | I.1 | None | None | [ ] |
| [I.3](tasks/deployment/I.3-reconcile-uspsadapter-against-the-usps-sandbox.md) | Reconcile `UspsAdapter` against the USPS sandbox | 0.2, 4.4, I.1 | None | None | [ ] |
| [7.1](tasks/batch-07/7.01-integration-test-harness.md) | Integration test harness | 4.5, 6.5 | None | 7.7–7.10 | [ ] |
| [7.2](tasks/batch-07/7.02-ingestion-integration-rows.md) | Ingestion integration rows | 7.1 | None | 7.3–7.10 | [ ] |
| [7.3](tasks/batch-07/7.03-next-step-integration-rows.md) | Next-step integration rows | 7.1 | None | 7.2, 7.4–7.10 | [ ] |
| [7.4](tasks/batch-07/7.04-eligibility-and-schedule-integration-rows.md) | Eligibility and schedule integration rows | 7.1 | None | 7.2, 7.3, 7.5–7.10 | [ ] |
| [7.5](tasks/batch-07/7.05-refresh-and-cancel-integration-rows.md) | Refresh and cancel integration rows | 7.1 | None | 7.2–7.4, 7.6–7.10 | [ ] |
| [7.6](tasks/batch-07/7.06-cross-cutting-integration-rows.md) | Cross-cutting integration rows | 7.1 | None | 7.2–7.5, 7.7–7.10 | [ ] |
| [7.7](tasks/batch-07/7.07-the-return-method-choice-flow.md) | The return-method choice flow | 3.14, 6.8 | 7.8, 7.9, 7.10 | 7.1–7.6 | [ ] |
| [7.8](tasks/batch-07/7.08-derive-label-carrier-three-sources-in-order.md) | `derive_label_carrier` — three sources, in order | 7.7 | 7.7, 7.9, 7.10 | 7.1–7.6 | [ ] |
| [7.9](tasks/batch-07/7.09-print-affirmation-pickup-offer-and-consent.md) | Print affirmation, pickup offer, and consent | 4.10, 4.13, 7.8 | 7.7, 7.8, 7.10 | 7.1–7.6 | [ ] |
| [7.10](tasks/batch-07/7.10-cancellation-orchestration.md) | Cancellation orchestration | 7.9 | 7.7, 7.8, 7.9 | 7.1–7.6 | [ ] |
| [8.1](tasks/batch-08/8.01-entrypoints-content-ts.md) | `entrypoints/content.ts` | 3.9, 3.13, 5.6 | None | 8.3 | [ ] |
| [8.2](tasks/batch-08/8.02-entrypoints-background-ts-the-worker-wiring-graph.md) | `entrypoints/background.ts` — the worker wiring graph | 3.17, 4.12, 5.6, 7.10, 8.1 | None | 8.3 | [ ] |
| [8.3](tasks/batch-08/8.03-popup-shell-ranked-list-scan-gesture-permission.md) | Popup shell, ranked list, scan gesture, permission offer | 3.11, 3.17, 8.2 | 8.4, 8.5 | None | [ ] |
| [8.4](tasks/batch-08/8.04-popup-return-surfaces-choice-affirmation-stuck.md) | Popup return surfaces — choice, affirmation, stuck | 8.3 | 8.3, 8.5 | None | [ ] |
| [8.5](tasks/batch-08/8.05-popup-pickup-calendar-clear-all-and-the-simulated.md) | Popup pickup, calendar, clear-all, and the simulated-booking marker | 3.12, 4.12, 8.4 | 8.3, 8.4 | None | [ ] |
| [8.6](tasks/batch-08/8.06-walk-the-whole-product-by-hand-in-a-real-browser.md) | Walk the whole product by hand in a real browser | 8.5 | None | None | [ ] |
| [9.1](tasks/batch-09/9.01-end-to-end-extension-test-harness.md) | End-to-end extension test harness | 8.6 | None | None | [ ] |
| [9.2](tasks/batch-09/9.02-ingestion-and-permission-rows.md) | Ingestion and permission rows | 9.1 | None | 9.3–9.7 | [ ] |
| [9.3](tasks/batch-09/9.03-driving-rows.md) | Driving rows | 9.1 | None | 9.2, 9.4–9.7 | [ ] |
| [9.4](tasks/batch-09/9.04-state-machine-and-terminal-rows.md) | State machine and terminal rows | 9.1 | None | 9.2, 9.3, 9.5–9.7 | [ ] |
| [9.5](tasks/batch-09/9.05-pickup-rows.md) | Pickup rows | 9.1 | None | 9.2–9.4, 9.6, 9.7 | [ ] |
| [9.6](tasks/batch-09/9.06-cancellation-rows.md) | Cancellation rows | 9.1 | None | 9.2–9.5, 9.7 | [ ] |
| [9.7](tasks/batch-09/9.07-platform-rows.md) | Platform rows | 9.1 | None | 9.2–9.6 | [ ] |
| [10.1](tasks/batch-10/10.01-prod-bundle-assertion-in-ci.md) | Prod-bundle assertion in CI | 1.4, 8.5 | None | 10.2, 10.3 | [ ] |
| [10.2](tasks/batch-10/10.02-requirement-and-configuration-citation-sweep.md) | Requirement and configuration citation sweep | 7.6, 9.7 | None | 10.1, 10.3 | [ ] |
| [10.3](tasks/batch-10/10.03-enforce-the-module-dependency-graphs.md) | Enforce the module dependency graphs | 6.5, 8.5 | None | 10.1, 10.2 | [ ] |
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
    1.2  WXT project scaffold and MV3 manifest                                 [extension]
 →  2.4  `src/types/` — entities, session, and the state enums                 [extension/src/types]
 →  4.6  `src/storage/` — key layout, defensive read, rebuild, and the barrel  [extension/src/storage]
 →  4.7  `StorageCoordinator.transact` — the serialising queue                 [extension/src/storage]
 →  4.9  `ReturnRepository`                                                    [extension/src/storage]
 →  6.6  `ReturnDriver` — construction, `transition`, and `start`              [extension/src/driver]
 →  6.7  State machine edges and rehydration                                   [extension/src/driver]
 →  6.8  Selector-first step loop and the model fallback                       [extension/src/driver]
 →  7.7  The return-method choice flow                                         [extension/src/driver]
 →  7.8  `derive_label_carrier` — three sources, in order                      [extension/src/driver]
 →  7.9  Print affirmation, pickup offer, and consent                          [extension/src/driver]
 → 7.10  Cancellation orchestration                                            [extension/src/driver]
 →  8.2  `entrypoints/background.ts` — the worker wiring graph                 [extension/entrypoints]
 →  8.3  Popup shell, ranked list, scan gesture, permission offer              [extension/entrypoints/popup]
 →  8.4  Popup return surfaces — choice, affirmation, stuck                    [extension/entrypoints/popup]
 →  8.5  Popup pickup, calendar, clear-all, and the simulated-booking marker   [extension/entrypoints/popup]
 →  8.6  Walk the whole product by hand in a real browser                      [docs/]
 →  9.1  End-to-end extension test harness                                     [extension/tests/integration]
 →  9.7  Platform rows                                                         [extension/tests/integration]
 → 10.2  Requirement and configuration citation sweep                          [repository root]
```

**Critical path length:** 20 tasks.

**Derived from the task files.** The chain is the longest path through the `prerequisites`
graph; `conflicts_with` is an undirected mutex, not an edge, so it orders nothing here.
8 distinct chains share that length; the one shown starts at the lowest-numbered
deepest task and walks back by the lowest-numbered prerequisite still on a maximal chain.

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

**It runs entirely through the extension.** The server's own longest chain is twelve tasks — fifteen
distinct chains tie at that length, and the tie-break used for the floor above picks 1.1 → 2.1 →
3.1 → 3.2 → 3.7 → 5.1 → 6.2 → 6.3 → 6.4 → 6.5 → 7.1 → 7.2. The server finishes early and waits. If
only one agent is available, start it on the extension; if two, the server track is the one that can
afford to be interrupted.

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
| 4 | A, B, C, C', D, E | server ∥ extension | 4.3–4.5 (`app/carriers/usps/__init__.py`); 4.6 → 4.7 → **{4.8 ∥ 4.9 ∥ 4.10 ∥ 4.11}** → 4.12 | The storage chain is still the batch's long pole, but four slots instead of seven |
| 5 | A, B, C, D, E | server ∥ extension | 5.4 ↔ 5.5 (`src/driver/index.ts`) | Server services are mutually independent |
| 6 | A, B | server ∥ extension | 6.1–6.4 (`app/routes/__init__.py`); **6.6 → 6.7 → 6.8 serial** (`src/driver/driver.ts`); 6.5 needs all four routes and 4.14 | Last batch where the two workspaces are still independent |
| — | Deployment | I.1 → I.2, I.3 ∥ I.2 | None — `infra/` is untouched by every other task | Opens after 6.5; runs concurrently with Batches 7–9 and gates nothing in them |
| 7 | A, B, C | server integration ∥ extension driver flows | 7.7–7.10 serial (`src/driver/driver.ts`); 7.2–7.6 mutually free | 7.2–7.6 are five agents on five files; 7.7–7.10 is one agent |
| 8 | A, B, Gate | Mostly serial | 8.3–8.5 share the popup shell and route table | 8.1 → 8.2 → 8.3 → 8.4 → 8.5 → 8.6; 8.6 is a human at a browser, not an agent |
| 9 | A, B | 9.2–9.7 all ∥ after 9.1 | None — one file each | Six agents can run the integration rows at once |
| 10 | A, B, C | 10.1 ∥ 10.2 ∥ 10.3 | None | CI enforcement; 10.2 needs 7.6 and 9.7 to have landed |

**Derived from the task files.** The table above is authored analysis; the counts and
conflict pairs below are generated from task frontmatter and will follow the task files
if either changes.

| Batch | Tasks | Track headings | Conflict pairs |
|-------|-------|----------------|----------------|
| 0 | 3 | 3 (A, B, C) | None |
| 1 | 5 | 4 (A, B, C, D) | 1.2 ↔ 1.4 |
| 2 | 8 | 7 (A, B, C, D, E, F, G) | 2.6 ↔ 2.7 |
| 3 | 18 | 11 (A, B, C, I, D, E, F, G, J, H, K) | 3.1 ↔ 3.2, 3.1 ↔ 3.3, 3.1 ↔ 3.4, 3.2 ↔ 3.3, 3.2 ↔ 3.4, 3.3 ↔ 3.4, 3.9 ↔ 3.10, 3.13 ↔ 3.14, 3.15 ↔ 3.16 |
| 4 | 14 | 5 (A, B, E, C, D) | 4.3 ↔ 4.4, 4.3 ↔ 4.5, 4.4 ↔ 4.5, 4.6 ↔ 4.7, 4.7 ↔ 4.12 |
| 5 | 6 | 5 (A, B, C, D, E) | 5.4 ↔ 5.5 |
| 6 | 8 | 2 (A, B) | 6.1 ↔ 6.2, 6.1 ↔ 6.3, 6.1 ↔ 6.4, 6.2 ↔ 6.3, 6.2 ↔ 6.4, 6.3 ↔ 6.4, 6.6 ↔ 6.7, 6.6 ↔ 6.8, 6.7 ↔ 6.8 |
| Deployment | 3 | 0 (—) | None |
| 7 | 10 | 3 (A, B, C) | 7.7 ↔ 7.8, 7.7 ↔ 7.9, 7.7 ↔ 7.10, 7.8 ↔ 7.9, 7.8 ↔ 7.10, 7.9 ↔ 7.10 |
| 8 | 6 | 3 (A, B, Gate) | 8.3 ↔ 8.4, 8.3 ↔ 8.5, 8.4 ↔ 8.5 |
| 9 | 7 | 2 (A, B) | None |
| 10 | 3 | 3 (A, B, C) | None |

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
| FR-3.4.1 | 2.1, 3.5, 4.4, 4.14, 5.3, 6.4, 7.9, I.3 | in-task (2.1, 3.5, 4.4, 4.14, 5.3, 6.4, 7.9, I.3) | 7.4, 9.5 |
| FR-3.4.2 | 4.14, 7.9 | in-task (4.14, 7.9) | 9.5 |
| FR-3.4.3 | 3.4, 4.4, 4.11, 5.3, 7.9, 8.5 | in-task (3.4, 4.4, 4.11, 5.3, 7.9, 8.5) | 9.5 |
| FR-3.4.4 | 5.3, 7.9 | in-task (5.3, 7.9) | 7.4, 9.5 |
| FR-3.4.5 | 3.4, 4.4, 4.10, 5.3, 7.9, 8.5, I.3 | in-task (3.4, 4.4, 4.10, 5.3, 7.9, 8.5, I.3) | 7.4, 9.5 |
| FR-3.4.5a | 3.4, 4.10, 7.9, 8.5 | in-task (3.4, 4.10, 7.9, 8.5) | 9.5 |
| FR-3.4.5b | 4.14, 8.5 | in-task (4.14, 8.5) | — |
| FR-3.4.6 | 4.4, 4.10, 5.3, 6.4, 7.10, 8.5, I.3 | in-task (4.4, 4.10, 5.3, 6.4, 7.10, 8.5, I.3) | 7.5, 9.6 |
| FR-3.4.7 | 7.9, 7.10, 8.5 | in-task (7.9, 7.10, 8.5) | 7.4, 7.5, 9.5, 9.6 |
| FR-3.4.8 | 2.1, 3.4, 3.5, 4.4, 4.11, 5.3, 6.4, 7.9, 8.5, I.3 | in-task (as listed) | 7.4, 9.5 |
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
| NFR-6.3 | 2.1, 2.8, 3.5, 3.16, 4.2, 4.5, 4.13, 4.14, 6.1, 6.7, 8.2 | in-task (as listed) | 9.7, 10.3 |
| NFR-6.4 | 2.5, 5.1, 6.8, 8.4 | in-task (2.5, 5.1, 6.8, 8.4) | 7.6, 9.7, I.2 |
| NFR-6.5 | 1.2, 1.4, 2.2, 3.16, 4.3, 4.6, 4.12, 5.6, 6.5, I.1 | in-task (as listed) | 10.1, 10.3, I.2 |
| NFR-6.6 | 2.2, 4.2, 4.3, 6.5, I.1 | in-task (2.2, 4.2, 4.3, 6.5, I.1) | I.2 |
| NFR-6.7 | 2.2, 6.1, 6.5, I.1 | in-task (2.2, 6.1, 6.5, I.1) | 7.6 |

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
| 1 | 5 | 4 | Scaffolding — both workspaces exist, CI runs, the extension IDs are pinned, coverage is enforced |
| 2 | 8 | 7 | Foundations — errors, config, logging, shared types, and the test fakes |
| 3 | 18 | 11 | Leaf modules — wire models, carrier protocol, extraction, ranking, validation, and the frozen contracts |
| 4 | 14 | 5 | Adapters and stores — Bedrock, USPS, the mock carrier, and the whole storage layer |
| 5 | 6 | 5 | Services — the three server services and the driver's collaborators |
| 6 | 8 | 2 | Assembly — routes and app wiring; the return state machine |
| — | 3 | 0 | **Deployment track** — the Lambda topology, a live smoke test, and USPS sandbox reconciliation |
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
