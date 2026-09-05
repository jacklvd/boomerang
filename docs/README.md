# Boomerang documentation

Each document has one job. Use this map to avoid treating repeated context or an old review as the
current implementation contract.

| Location | Purpose | Authority |
|---|---|---|
| [`SKETCH.md`](SKETCH.md) | Product problem, intended experience, priorities, and v1 boundary | Current product direction |
| [`RETURN_WORKFLOW.md`](RETURN_WORKFLOW.md) | Current normal flow and state ownership; clearly separated deferred interruption proposal | Current workflow contract except the marked proposal |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Technical shape, decision status, privacy baseline, and blockers | Current decisions for the migrated areas below |
| [`../design/boomerang-requirements.md`](../design/boomerang-requirements.md) | Testable functional and non-functional requirements | Current normative requirements |
| [`../design/boomerang-high-level-design.md`](../design/boomerang-high-level-design.md) | Components, data flows, security, and deployment shape | Current normative design |
| [`../design/boomerang-low-level-design.md`](../design/boomerang-low-level-design.md) | Modules, types, interactions, storage, wiring, and tests | Current refinement of the upstream design |
| [`../design/boomerang-data-model.md`](../design/boomerang-data-model.md) | Shared logical, wire, and extension-local models for parallel implementation | Current implementation contract for its stated scope |
| [`../design/boomerang-api-contract.md`](../design/boomerang-api-contract.md) | Dashboard and extension UI HTTP endpoints and examples | Current implementation contract for its stated scope |
| [`../plan/boomerang-decisions.md`](../plan/boomerang-decisions.md) | Current migration decisions plus clearly marked historical planning decisions | Current for the migration section; historical below it |
| [`../plan/boomerang-plan.md`](../plan/boomerang-plan.md) | Milestone order and workstream readiness | Current milestone/workstream plan |
| [`../plan/tasks/`](../plan/tasks/) | Previous task-level decomposition | Unreconciled historical planning material |
| [`../scripts/split-plan.py`](../scripts/split-plan.py) and [`../scripts/build-plan-index.py`](../scripts/build-plan-index.py) | Tooling for the previous task corpus | Dormant until the separate task-planning pass updates or retires it |
| [`../reviews/`](../reviews/) | Findings against specific earlier revisions | Historical evidence, not current authority |
| [`../.claude/artifacts/`](../.claude/artifacts/) | Raw research behind earlier decisions | Source material |

## Direction migration

The meeting decisions captured on 2026-09-05 intentionally change the earlier local-only,
USPS-oriented PoC. The documents in this folder, `design/`, the milestone plan, and the migration
section of the planning decision record are updated. The files under `plan/tasks/`, implementation,
and workspace guidance remain to be reconciled where they conflict.

For the following areas, the current docs take precedence until that reconciliation is complete:

- Google authentication for the Boomerang account
- a database-backed web dashboard as the main product surface
- normalized orders, prices, delivery dates, policy rules, deadlines, fees, preferences, and current
  return summaries stored in the database
- detailed workflow/session state and the latest safe checkpoint stored in extension local storage
- synchronous parsing as a provisional assumption and explicit blocker
- uninterrupted autofill in v1, with interruption/resumption kept outside the main plan as a
  deferred proposal
- agent-first return execution: every step sends a bounded, sanitized representation of the current
  live DOM to the agent for exactly one closed-tool proposal; trusted extension code validates and
  executes browser actions or records a validated terminal outcome, while bundled selectors remain
  resolution and validation aids only
- sanitized terminal-page representations may reach the agent, but raw label artifacts, QR
  contents, addresses, barcodes, and protected URLs must be removed before transmission
- retailer-produced QR outcomes and the persisted `qr_ready` status as priority 1; whether to store
  a QR representation is deferred
- Google Calendar API as priority 2, with separate Calendar consent and implementation topology
  deferred until that priority is taken up
- USPS pickup and all carrier-pickup controls excluded from v1

The current design remains authoritative for details not summarized above. The milestone plan has
been migrated, but the task-level decomposition has not. Do not begin implementation from a mixed
reading: use the current plan with these sources and treat `plan/tasks/` as historical input until
it is reconciled. The task splitting and index scripts target that same historical corpus; they are
not current validation gates and must not be used to validate the milestone plan until the separate
task-planning pass updates or retires them.

## Resolving disagreement

1. Working code and tests describe what the repository currently does, not necessarily the newly
   approved target. Keep implementation-status claims separate from product decisions.
2. For the migrated areas above, `SKETCH.md`, `RETURN_WORKFLOW.md`, and `ARCHITECTURE.md` define the
   target. The reconciled `design/` documents translate that target; the stale task set or current
   code cannot override it.
3. After reconciliation, requirements and the high-level design define what should be built; the
   low-level design refines them but does not overrule them.
4. `ARCHITECTURE.md` explains why a settled decision exists. `RETURN_WORKFLOW.md` owns behavioral
   sequencing and execution-state ownership. `SKETCH.md` stays at product-summary altitude.
5. If code and current design disagree, update the stale side in the same implementation change.

Review documents intentionally preserve what a reviewer saw at a particular revision. A finding in
`reviews/` may already be resolved, superseded by the 2026-09-05 direction, or still valid. Verify it
against the current source before treating it as an open blocker.

Current workspace status and repository conventions live in [`../AGENTS.md`](../AGENTS.md) and the
workspace-specific `AGENTS.md` files. Some of that guidance still reflects the pre-migration scope
and must be updated when work expands beyond this docs-only refinement.
