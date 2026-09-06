# Boomerang — Implementation Plan

> **Status:** Rebased on the product direction approved on 2026-09-05 and the current API and
> data-model contracts. This is a milestone/workstream plan, not a task tracker.
>
> **Task reconciliation required:** [`plan/tasks/`](tasks/) still describes the previous
> local-only, carrier-pickup-oriented architecture. Those files were intentionally not changed in
> this migration and are not the execution authority for the milestones below. Task counts,
> progress totals, batch barriers, makespan estimates, critical paths, conflict graphs, and
> task-level traceability remain withdrawn until a separate task-planning pass replaces or retires
> the stale task set. `scripts/split-plan.py` and `scripts/build-plan-index.py` target that same
> historical corpus; they are dormant, not current validation gates, until that pass updates or
> retires them.

## 1. Planning authority and boundaries

This plan translates the current product and design sources into delivery order:

1. [`docs/README.md`](../docs/README.md), [`docs/SKETCH.md`](../docs/SKETCH.md),
   [`docs/RETURN_WORKFLOW.md`](../docs/RETURN_WORKFLOW.md), and
   [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) own product direction and architecture.
2. [`design/boomerang-requirements.md`](../design/boomerang-requirements.md) owns testable
   requirements and the `ARCH-B*` blocker register.
3. The high- and low-level designs own component and implementation boundaries.
4. The API and data-model contracts own the stable v1 dashboard/extension UI wire shapes and
   shared invariants.
5. This document owns milestone order and workstream readiness. It does not fill an architecture
   blocker with a planning assumption.

The existing application and infrastructure scaffolds may support local development, but they do
not establish the target architecture. In particular, the former Lambda Function URL,
no-database topology is not a current production target. The production compute topology,
database product, network layout, hosting mode, secret store, environment split, and deployment
pipeline remain delivery decisions to make after the relevant data, authentication, AI-runtime,
and bridge boundaries are sufficiently settled. Priority-2 Calendar does not block the core-v1
topology; that topology must preserve a clean integration boundary for the later `ARCH-B5` design.

## 2. Delivery target

### Core v1

Core v1 delivers:

- Sign in with Google, with the account keyed by Google's stable OpenID Connect `sub` claim;
- a database-backed web dashboard as the durable product home;
- a visible extension connection state, composed outside the current server dashboard response;
- user-initiated Chrome page scanning with the minimal Manifest V3 permission posture;
- extension-to-server submission of bounded, sanitized retailer-page data;
- validated normalization and persistence of account orders, items, policy facts, dates, prices,
  deadlines, fees, preferences, and return summaries;
- database-derived dashboard metrics, urgency, recommendations, and next actions;
- one visible, supervised, uninterrupted return run;
- an agent-first loop in which every step requests exactly one proposal from the closed tool
  vocabulary and trusted extension code validates it before execution or publication;
- user selection of every return method and explicit confirmation of irreversible actions;
- durable `in_progress` and `label_ready` summary outcomes; and
- honest manual handoff when the page, model, or workflow cannot proceed safely.

### Priority 1

Priority 1 adds the durable `qr_ready` outcome. V1 stores the status only. It does not persist or
transmit a QR image, token, URL, barcode, or other QR representation as an account artifact.

### Priority 2

Google Calendar follows the core return flow. It requires separate incremental authorization when
the user chooses **Add to calendar**, writes a deadline or follow-up event, and does not read
availability. Component ownership, wire contracts, OAuth scope, token custody, refresh,
revocation, and update behavior remain gated by `ARCH-B5`.

### Deferred from v1

- USPS, UPS, FedEx, retailer, or paid pickup integration;
- pickup eligibility, booking, confirmation, refresh, cancellation, and tracking;
- Gmail API access or Gmail scraping;
- user-controlled Stop/Continue and interrupted-run reconciliation or resumption;
- unattended retailer-account access;
- storage of QR or label artifacts;
- browsers other than Chrome; and
- asynchronous normalization unless evidence gathered under `ARCH-B2` requires it.

## 3. Architecture baseline

### 3.1 Surface and authority split

| Concern | Authoritative home | Planning rule |
|---|---|---|
| Google-linked account, normalized orders/items/policies, preferences, and current return summary | Database | Dashboard and account APIs read this store; the extension is not a local account database |
| Detailed workflow/session state, tab context, selected method, fields filled, attempts, and latest safe checkpoint | `chrome.storage.local` | Do not duplicate this as authoritative server workflow state |
| Retailer login and credentials | Browser session | The backend cannot initiate retailer access or act without extension-supplied page state |
| Raw DOM and bounded, sanitized DOM representations | No durable store | Process transiently and exclude from databases, local workflow records, logs, analytics, and durable model logs |
| Extension connection and dashboard command path | Undecided | Treat as `ARCH-B6`; do not invent a database table or transport |
| Calendar credentials and event metadata | Undecided | No implementation model before priority 2 and `ARCH-B5` |

The database return summary is a minimal dashboard projection, not a copy of the browser workflow.
The current state vocabulary is `not_started`, `in_progress`, `qr_ready`, `label_ready`,
`handed_to_carrier`, and `complete`. Writes to `handed_to_carrier` and `complete` remain
blocked by `ARCH-B3` and `ARCH-B8`, respectively.

### 3.2 Browser-to-server flow

The server sees retailer data only after an explicit browser action causes the extension to select,
bound, sanitize, and transmit the relevant live-page representation. The server validates the
authenticated account, invokes normalization, validates model output, persists only normalized
records, and discards the transient source representation after success or failure.

The current v1 account API contract intentionally does not define ingestion or agent endpoints.
Those interfaces stay behind application clients until `ARCH-B2` settles payload, observation,
latency, timeout, retry, sync/async, and hosting-fit decisions.

### 3.3 Return execution

Every return-flow iteration must:

1. read and sanitize the current live DOM after the preceding action settles;
2. request exactly one agent proposal;
3. accept only `click`, `select_option`, `fill`, `pause_for_user`, `report_stuck`, or
   `report_outcome`;
4. validate the proposal in trusted extension code against the same live page, target restrictions,
   and user-confirmation rules; and
5. execute one validated reversible action, pause or hand off, or publish one validated terminal
   outcome.

Bundled selectors may assist page recognition, target resolution, and validation. They do not
plan an action, advance a step, or become a fallback when the agent is unavailable. A stale,
invalid, or unsupported proposal executes and publishes nothing.

The user reviews suggested reasons, sees all visible methods and known prices, chooses the return
method, and confirms final submission. Preferences rank and explain choices; they never hide or
select them.

### 3.4 Outcomes and dashboard projections

The retailer remains the authority that produces a QR code or printable label. In v1,
`report_outcome` carries only `qr_ready` or `label_ready`, and the extension validates the
terminal page before publishing the summary. No artifact crosses the summary API.

Dashboard `NextAction`, urgency, `closing_soon_count`, returnable value, and other metrics are
server-derived advisory projections governed by the current data-model contract. Client invocation
availability is composed separately with extension connectivity and local capabilities. Dashboard
filters affect the candidate list and pagination, not account-wide metrics.

### 3.5 Identity, permissions, and privacy

- Initial Google sign-in requests only identity information; it grants neither Calendar nor Gmail
  access and is not a retailer credential.
- Account access is scoped through the authenticated principal. Clients do not choose an account by
  submitting an `account_id`.
- The extension initially declares only `activeTab`, `scripting`, and `storage`.
- First-page access follows an explicit gesture such as **Scan this page**. A standing retailer host
  permission may be requested only afterward, in context, and declining it preserves scan-on-click.
- Retailer cookies, authorization headers, passwords, payment fields, file inputs, raw QR/label
  artifacts, addresses, barcodes, and protected URLs do not cross the extension egress boundary.
- Product privacy copy must disclose Google identity, database storage, transient model processing,
  extension-local workflow state, and any later Calendar authorization accurately.

## 4. Workstream readiness

“Proceed now” means the current documents define enough boundary to plan and implement that work.
It does not make the stale files under `plan/tasks/` executable.

| Workstream | Readiness | Can proceed now | Gate or limit |
|---|---|---|---|
| Planning and contract fixtures | Proceed now | Rebuild task decomposition from current requirements; create fixtures for the stable account API and data models | Do not reuse old counts or endpoint fixtures as current truth |
| Google identity and account isolation | Proceed now behind an adapter | `sub`-keyed account model, identity-only consent, authenticated account boundary, isolation tests | Session transport and credential-exchange route are intentionally not frozen |
| Database and account API | Proceed now | Account/order/item/policy/preference/summary persistence, current `/v1` read/write contract, baseline account deletion | Physical schema choices and lifecycle beyond the baseline are limited by `ARCH-B4` |
| Web dashboard | Proceed now | Database-backed list/detail/metrics/preferences/privacy views and current advisory projections | Live connection and return-start controls require `ARCH-B6` |
| Extension platform and safety | Proceed now in generic form | MV3 scaffold, permission flow, local workflow schema, extraction boundary, egress guard, validator, test fakes | Retailer URL/DOM behavior requires `ARCH-B7`; numeric AI limits require `ARCH-B2` |
| Normalization pipeline | Partially ready | Model gateway seam, strict output schemas, transient-processing and persistence boundaries | Final request/job contract, limits, retry/timeout, and hosting fit require `ARCH-B2`; retailer identity/reconciliation require `ARCH-B7` |
| Agent-first return loop | Partially ready | Closed tool union, local driver boundaries, user-choice and confirmation guards, proposal validation | Runtime wire contract `ARCH-B2`; interruption acceptance `ARCH-B1`; retailer behavior `ARCH-B7` |
| Dashboard-to-extension bridge | Blocked | UI seams and enumerated capability boundary only | Transport, account/browser binding, addressing, revocation, and acknowledgements require `ARCH-B6` |
| QR and label outcomes | Partially ready | Status-only models, summary publication, artifact rejection, generic terminal validator | Real outcome recognition and acceptance require `ARCH-B7` |
| Carrier handoff and `complete` | Blocked | Defensive read/render behavior only | `handed_to_carrier` requires `ARCH-B3`; `complete` requires `ARCH-B8` |
| Privacy, deletion, and lifecycle | Partially ready | Never-persist rules, safe logging, baseline account deletion, local clear semantics | Detailed retention, cleanup, backups, recovery, and token lifetimes require `ARCH-B4` |
| Test and delivery controls | Proceed now | Account-contract tests, unit/integration harnesses, privacy checks, CI, real-browser acceptance shape | Retailer and latency acceptance wait on `ARCH-B7` and `ARCH-B2` |
| Production deployment | Limited to discovery and local support | Keep local development working; identify candidate topology constraints | Do not carry forward the no-database Lambda plan; target topology is not yet selected |
| Google Calendar | Deferred, priority 2 | Preserve only product boundary and incremental-consent seam | Detailed planning requires `ARCH-B5` |
| Carrier pickup | Deferred from v1 | No active implementation work | Requires a future scope and carrier contract; do not revive old pickup tasks |

## 5. Milestone sequence

Milestones are ordered by product risk and dependency, not by the obsolete task batches. Workstreams
inside a milestone may proceed in parallel when they do not depend on the same open gate.

### Milestone 0 — Planning reset and gate ownership

**Status:** milestone direction is current; task-level reconciliation remains pending.

Outcomes:

- use the current requirements, designs, API contract, and data model as the only active design
  baseline;
- classify every workstream as proceed-now, partial, blocked, priority 2, or deferred;
- carry `ARCH-B1` through `ARCH-B8` into milestone exits instead of hiding them in task details;
- remove the old plan's task totals, schedule math, batch barriers, and traceability claims; and
- perform a later, separate reconciliation of `plan/tasks/**` before restoring a task tracker.

Exit condition: a future task-planning pass can decompose the milestones without consulting the old
USPS-first critical path as authority.

### Milestone 1 — Authenticated account and contract foundation

Build the durable account boundary first so the dashboard and extension share real identifiers and
contracts instead of treating extension storage as the product database.

Workstreams:

- Google identity integration keyed by `sub`, with identity-only consent;
- authentication/session adapter and account-scoped service boundaries;
- logical persistence for Account, Order, OrderItem, ReturnPolicy, PreferenceSet, and ReturnSummary;
- the stable v1 account API: profile, dashboard aggregate, item detail, preferences, supported
  return-summary publication, and account deletion;
- strict shared enum, date, money, null, error, request-ID, and account-ownership behavior; and
- canonical API examples consumed by client fixtures and server contract tests.

Exit evidence:

- cross-account item access is indistinguishable from not found;
- no response exposes Google `sub` or accepts a caller-selected account;
- the current API examples validate against the shared model;
- supported summary transitions are monotonic and repeatable as specified; and
- `handed_to_carrier` and `complete` writes remain explicitly blocked.

This milestone can proceed now. Choosing cookie versus bearer session transport and the Google
credential-exchange route is a contained integration decision; it must not change stable v1 bodies.

### Milestone 2 — Database-backed dashboard vertical slice

Deliver the product home against account data before building retailer automation.

Workstreams:

- authenticated list, detail, metrics, urgency legend, and preference screens;
- exact `NextAction`, urgency, closing-soon, in-progress, handoff, and returnable-value projections;
- honest rendering of unknown deadline, price, fee, eligibility, and multiple currencies;
- dashboard privacy and baseline account-deletion surfaces; and
- a client-side extension-state seam that can render disconnected/unknown without inventing a
  server field.

Exit evidence:

- the dashboard reads the database-backed API, never extension order history;
- every normative state-to-action mapping and closing-soon boundary is contract-tested;
- list filters do not alter account-wide metrics; and
- QR/label status language does not imply carrier pickup or stored artifacts.

The data UI can proceed now. A live connected state and dashboard-initiated return remain gated by
`ARCH-B6`.

### Milestone 3 — User-initiated scan, normalization, and persistence

Establish the one permitted path from a retailer session into durable account data.

Workstreams that can begin now:

- minimal MV3 manifest and explicit scan gesture;
- optional contextual host-permission flow;
- content-script extraction, bounding, sanitization, and fail-closed egress boundaries;
- strict normalized output validation and account-scoped transactional persistence; and
- pending, failure, rescan, and unsupported-page UI states that do not fabricate a partial success.

Gated completion work:

- settle payloads, observation boundaries, latency, timeout, retry, sync/async, and hosting fit under
  `ARCH-B2`;
- choose the first retailer under `ARCH-B7`; then create its URL/DOM recognizer, identity and rescan
  rules, synthetic/safe fixtures, and browser acceptance criteria.

Exit evidence:

- one explicit scan creates or updates normalized database records for the authenticated account;
- the backend cannot fetch the retailer page independently;
- raw and bounded sanitized page representations are absent from durable stores and logs; and
- failures store no fabricated successful parse.

### Milestone 4 — Agent-first supervised return execution

Build the browser workflow around the current authority split rather than the former selector-first
driver.

Workstreams that can begin now:

- extension-local WorkflowSession and safe-checkpoint models with defensive schema reads;
- closed tool schemas and a validator that rejects missing, multiple, free-form, stale, sensitive,
  or unsupported proposals;
- visible tab control and one-action execution boundaries;
- user review of suggested reasons, all visible methods and prices, and final confirmation; and
- manual-handoff behavior that leaves the retailer page usable and makes no resume promise.

Gated completion work:

- `ARCH-B2` for the per-step agent request and response contract;
- `ARCH-B7` for retailer steps, targets, and live-page validation;
- `ARCH-B6` for account-bound dashboard start/focus behavior; and
- `ARCH-B1` for exact interrupted-run fallback and acceptance criteria.

Exit evidence:

- every automated step begins with a fresh agent request from current sanitized DOM;
- selectors cannot construct or execute an action independently;
- the extension executes at most one validated action for one observation;
- password, payment, and file-upload fills are impossible; and
- an invalid, stale, timed-out, or divergent step executes nothing and hands control to the user.

### Milestone 5 — Retailer outcomes and core v1 acceptance

Connect the supervised loop to durable, artifact-free dashboard outcomes.

Workstreams:

- publish `in_progress` after validating the live flow;
- validate and publish the core retailer-produced `label_ready` outcome;
- as the priority-1 addition, validate and publish the retailer-produced `qr_ready` outcome;
- remove QR contents, raw label artifacts, addresses, barcodes, and protected URLs before terminal
  model egress;
- keep detailed workflow truth local when summary synchronization fails; and
- run the chosen retailer from explicit scan through user confirmation and a supported result in a
  real Chrome session.

Exit evidence:

- the terminal agent tool carries only `qr_ready` or `label_ready`, never an artifact;
- core acceptance verifies `label_ready` support and honest manual handoff for unsupported outcomes;
- priority-1 acceptance additionally verifies `qr_ready` support;
- the dashboard reflects validated summaries without claiming pickup;
- unknown outcomes leave the page open and publish no stronger claim; and
- the core flow passes real-browser, account-isolation, security, privacy, and failure-path review.

This milestone depends on the integrated portions of `ARCH-B1`, `ARCH-B2`, `ARCH-B6`, and
`ARCH-B7`. `ARCH-B3` and `ARCH-B8` do not block QR/label acceptance; they keep carrier handoff
and `complete` outside the accepted write path.

### Milestone 6 — Lifecycle and release readiness

Harden the completed core flow without reviving the former deployment plan.

Workstreams:

- validate product and Chrome Web Store disclosures against actual data flows;
- verify account deletion of active primary records and local clearing semantics;
- enforce log, analytics, and model-invocation redaction;
- exercise model, database, network, extension-disconnected, stale-page, and summary-sync failures;
- enforce current manifest, contract, state-ownership, and module-boundary checks in CI; and
- select and validate a production deployment architecture compatible with the database,
  authentication, AI-runtime, and bridge decisions while preserving a clean boundary for the later
  priority-2 Calendar design.

The baseline security and deletion work can proceed earlier. Final retention, cleanup, backup,
recovery, and token-lifetime acceptance remains gated by `ARCH-B4`. No current estimate or
deployment critical path is asserted before the production topology and reconciled tasks exist.

### Milestone 7 — Google Calendar, priority 2

Begin only after core v1 and after `ARCH-B5` is resolved. Define component ownership, the narrow
Calendar scope, credential custody, wire contracts, refresh/revocation, event creation, and any
update behavior before implementation. Calendar failure must not invalidate a return or block the
core flow.

Carrier pickup is not a milestone in this plan. It requires a future product decision and a new
carrier contract before planning begins.

## 6. Architecture gates

| Gate | Decision still required | Work that remains blocked | Work that may continue |
|---|---|---|---|
| `ARCH-B1` | Exact behavior and acceptance after user, tab, page, or worker interruption | Final interruption flow and browser acceptance | Local checkpoints, conservative no-action behavior, uninterrupted happy path |
| `ARCH-B2` | Realistic payloads and latency; normalization and per-step request shapes; budgets, timeout, retry, sync/async, and hosting fit | Final AI wire contracts and integrated runtime | Model gateway seams, strict schemas, egress guards, contract-independent validation |
| `ARCH-B3` | Accepted evidence and publisher for `handed_to_carrier` | Handoff writes and their acceptance tests | Defensive reads and carrier-neutral UI copy |
| `ARCH-B4` | Record/checkpoint/token lifetimes, single-order deletion, cleanup, backups, and recovery | Detailed lifecycle jobs and policy acceptance | Never-persist rules, active-primary-record account deletion, local clearing |
| `ARCH-B5` | Calendar ownership, wire contract, scope, token custody, refresh/revocation, and updates | All Calendar implementation | Core return flow and a nonfunctional priority-2 seam |
| `ARCH-B6` | Secure dashboard-to-extension binding, addressing, command transport, acknowledgements, and revocation | Live connection state and dashboard start/focus flow | Dashboard data UI and an enumerated client interface |
| `ARCH-B7` | First retailer | Adapter, selectors/hints, policy assumptions, fixtures, rescan rules, and real-browser acceptance | Retailer-agnostic extension, validator, local store, and test harness boundaries |
| `ARCH-B8` | Meaning, evidence, and legal transitions for `complete` | `complete` writes and acceptance tests | Defensive reads only; QR/label outcomes remain independent |

No gate is resolved by naming a task, creating a placeholder enum, or relying on the behavior of the
old plan.

## 7. Verification and traceability posture

Verification is organized by requirement family until task-level reconciliation is complete.

| Requirement family | Milestone verification home |
|---|---|
| `AUTH-*` | Milestone 1 identity, account isolation, and scope-separation tests |
| `CONN-*` | Milestones 2 and 4 after `ARCH-B6` |
| `EXT-*` | Milestone 3 manifest, gesture, permission, and browser tests; retailer rows after `ARCH-B7` |
| `INGEST-*` | Milestone 3 validation, persistence, transient-data, and failure tests; runtime rows after `ARCH-B2` |
| `DATA-*` | Milestones 1 and 4 ownership, schema, summary, and local-workflow tests |
| `DASH-*`, `PREF-*` | Milestone 2 component and projection contract tests |
| `RETURN-*` | Milestone 4 unit and browser tests, limited by `ARCH-B1`, `ARCH-B2`, and `ARCH-B7` |
| `OUTCOME-*` | Milestone 5 terminal sanitizer, live validation, artifact rejection, and publication tests |
| `CAL-*` | Milestone 7 after `ARCH-B5` |
| `PRIV-*`, `SEC-*`, `REL-*`, `PERF-*`, `COMP-*` | Cross-cutting evidence in Milestones 1–6, with blocked portions named explicitly |

The stable account contract must at minimum test the canonical examples, every supported
state-to-action mapping, `not_started` with ineligible and expired projections, unknown eligibility
and deadline, closing-soon boundaries at `-1`, `0`, the configured maximum, and maximum plus one,
list-filter independence of account-wide metrics, preference replacement, supported summary
transitions including repeatable ready states, blocked writes, account isolation, and artifact-free
responses and logs.

This is workstream-level traceability only. It is not evidence that the current files under
`plan/tasks/` cover the rewritten requirements.

## 8. Required future task-planning pass

The next planning pass must review every file under `plan/tasks/**` against this document. It must:

1. retire carrier eligibility, pickup scheduling, confirmation, cancellation, carrier mocks, and
   USPS sandbox work from the active v1 task set;
2. replace extension-owned order/history/preferences work with Google identity, database,
   account-API, and dashboard work;
3. replace selector-first/model-fallback tasks with the every-step agent loop and trusted local
   validation;
4. replace the old ingestion, next-step, pickup, and client-version fixtures with the current
   stable v1 account API and keep AI/bridge contracts gated;
5. split database summary work from extension-local WorkflowSession/checkpoint work;
6. add status-only QR/label terminal outcomes and the terminal egress guard;
7. defer Calendar implementation to priority 2 under `ARCH-B5` and remove template-URL work from
   core v1;
8. keep the bridge, retailer adapter, handoff, complete, lifecycle, and AI-runtime task detail behind
   their named `ARCH-B*` gates;
9. replace the fixed Lambda/no-database deployment track with a topology-selection and validation
   effort when its prerequisites are known; and
10. regenerate task identifiers, prerequisites, conflicts, progress tracking, estimates, critical
    paths, and requirement traceability from the reconciled task set rather than editing the old
    numbers in place.

Until that pass lands, the old task files are migration input and historical context only. Their
unchecked boxes do not identify work that is safe to start, and completing one does not establish
progress against this plan.

## 9. Definition of done

Core v1 is done when a user can sign in with Google, see account-scoped database-backed return data,
scan a supported retailer page through an explicit extension gesture, persist validated normalized
records without persisting page content, start and observe an agent-first return, choose among all
visible methods and prices, confirm the irreversible submission, and see a validated `label_ready`
status without Boomerang storing the artifact or claiming carrier pickup. Core v1 requires verified
support for `label_ready` and honest manual handoff for unsupported outcomes. Priority 1 additionally
requires verified support for `qr_ready`.

The definition also requires honest failure and manual-handoff behavior, extension/database state
ownership tests, current contract tests, privacy and deletion evidence, and real-browser acceptance
for the retailer selected under `ARCH-B7`.

It does not require Calendar, carrier pickup, interrupted-run resumption, `handed_to_carrier`, or
`complete`. Those remain priority 2, deferred, or blocked as stated above.
