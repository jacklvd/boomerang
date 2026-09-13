# Boomerang — Planning Decision Record

> **Current direction:** The migration decision dated 2026-09-06 is the active planning baseline.
> The 2026-08-27 and 2026-09-01 decisions are preserved below as historical context. When they
> conflict, the migration decision and the current product/design documents supersede them.

## Current migration decision — 2026-09-06

### Why this decision exists

The product direction changed after the original task plan was reviewed. The old plan assumed an
extension-local account history, a selector-first driver, a USPS or third-party pickup path, a
Calendar template in the core flow, and a Lambda Function URL with no database. The current product
instead has a database-backed web dashboard, Google identity, browser-sourced ingestion, an
agent-first supervised return loop, split database/local state ownership, and retailer-produced QR
or printable-label outcomes.

This section records that migration without erasing why the earlier plan existed. The current
authority is [`docs/README.md`](../docs/README.md), [`docs/SKETCH.md`](../docs/SKETCH.md),
[`docs/RETURN_WORKFLOW.md`](../docs/RETURN_WORKFLOW.md),
[`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md), and the current requirements and design
contracts. [`boomerang-milestones.md`](boomerang-milestones.md) is the human-authored,
authoritative milestone/workstream plan. [`boomerang-plan.md`](boomerang-plan.md) is reserved for a
future generated task-level plan and index; no generated task plan is currently published.
[`plan/tasks/**`](tasks/) remains unreconciled historical planning material.

The findings in [`docs/spikes/retailer-flow.md`](../docs/spikes/retailer-flow.md) remain useful
research evidence, but its retargeting recommendations are not current product decisions. In
particular, Boomerang does not automatically choose a default reason or return method and does not
persist a QR representation in v1.

### Decision classifications

| Classification | Meaning in this record |
|---|---|
| **Accepted** | Current direction; implementation and future planning must preserve it |
| **Provisional** | The boundary is usable, but evidence or a contained implementation choice is still required |
| **Deferred** | Deliberately outside core v1; no active implementation design should be inferred |
| **Open / blocked** | A named architecture decision must be made before the affected contract or acceptance work can close |
| **Historical** | Preserved to explain the old plan; not current authority |

### Accepted architecture and scope decisions

| ID | Accepted decision | Consequence for planning |
|---|---|---|
| `MIG-01` | The web dashboard is the product home and reads authenticated account data from a database. | Replace extension-local dashboard history and the no-database plan with account persistence, APIs, and dashboard work. |
| `MIG-02` | Sign in with Google establishes the account, keyed by the stable OpenID Connect `sub` claim. Identity consent grants neither Gmail, Calendar, nor retailer access. | Add identity/account isolation early; never key identity by email and never add Gmail. |
| `MIG-03` | Retailer data originates only in the user's browser. The extension sends bounded, sanitized live-page data to the server for transient processing and validated normalization. | The server has no polling, background retailer access, or retailer credential. Ingestion is extension-to-server. |
| `MIG-04` | Database account state and extension-local browser workflow state have separate authority. | Store normalized orders, policies, preferences, and minimal summaries in the database; keep current step, tab, choices, attempts, and safe checkpoint in `chrome.storage.local`. |
| `MIG-05` | Every return-flow step is agent-first. The agent proposes exactly one closed tool call; trusted extension code validates before execution or outcome publication. | Remove selector-first and model-fallback work. Selectors may assist recognition, resolution, and validation only. |
| `MIG-06` | Recommendations do not grant authority. Preferences rank and explain; the user sees all visible methods and prices, chooses the method, edits the reason, and confirms irreversible actions. | Do not auto-select a return reason, method, or paid option. |
| `MIG-07` | Retailer-produced QR and printable-label outcomes are valid without pickup. V1 persists `qr_ready` or `label_ready` status, not the artifact. | Make terminal sanitization and summary publication part of the return flow; do not attach carrier semantics to either state. |
| `MIG-08` | The stable v1 HTTP contract currently covers dashboard sign-in and extension browser linking, account profile, dashboard aggregate, item detail, preferences, supported return-summary publication, and account deletion. The authentication routes joined it on 2026-09-13 under `MIG-15`. | Build dashboard and server fixtures from the current API/data contracts. Keep ingestion, agent, Calendar, and bridge routes outside this stable surface until their respective architecture gates close. Carrier pickup routes remain deferred and require a separate future product decision and carrier contract. |
| `MIG-09` | The extension keeps the minimal install posture: `activeTab`, `scripting`, and `storage`; first access follows a user gesture and optional standing retailer access is requested later in context. | Permission and review posture are core acceptance criteria. |
| `MIG-10` | Raw DOM, bounded sanitized DOM, retailer cookies and authorization credentials, sensitive retailer form fields, and raw QR/label artifacts have no durable home in Boomerang storage. | Add fail-closed egress, validation, logging, model-invocation, persistence, and privacy checks across milestones. |
| `MIG-11` | Core v1 is the database dashboard plus one visible, supervised, uninterrupted Chrome return run. QR status is priority 1. Calendar is priority 2. All carrier pickup is deferred. | Remove pickup and Calendar-template work from the core sequence; plan Calendar only after core and `ARCH-B5`. |
| `MIG-12` | The production topology is not selected. The former Lambda Function URL/no-VPC/no-database target cannot be carried forward because a durable database and authenticated account APIs are now required. | Continue local scaffolding only as scaffolding. Re-plan core-v1 deployment after the data, authentication, AI-runtime, and bridge constraints are sufficiently settled. Priority-2 Calendar does not block that work; the core topology must preserve a clean boundary for the later `ARCH-B5` design. |
| `MIG-13` | The old task graph is not synchronized with the current requirements. | Use milestone/workstream planning now; do not publish task totals, makespan, critical path, progress, or complete task traceability until `plan/tasks/**` is reconciled. |
| `MIG-14` | Planning authority flows from the current source documents to the human-authored milestone plan, then to approved tasks. | Keep the authoritative milestone source separate from the future generated task plan; generated task analysis must never redefine upstream product or architecture decisions. |
| `MIG-15` | **Extension-to-server authentication is server-brokered browser linking with proof-of-key redemption.** The extension is a public client of Boomerang, not of Google, and has no Google relationship at all. The extension presents an opaque bearer credential in `Authorization`; the dashboard presents a first-party `Secure; HttpOnly; SameSite=Lax` cookie with `Origin` matching on mutating routes. Both resolve to one account principal that also carries its client kind. Signing out of the dashboard revokes the extension grant linked from the same browser. Accepted 2026-09-13. **Scope amended 2026-09-13 by `MIG-19`: sign-out revokes every live extension grant on the account, in every linked browser.** The substance of this decision — that sign-out revokes — is unchanged and was never reopened; the same-browser clause above is superseded and retained as the record of what was first decided. | Build the pairing, redemption, refresh, revocation and linked-browsers routes, the Google credential exchange, the dashboard link-approval page and the linked-browsers list with a disconnect control. The extension manifest does not change, and must not. Never add a Google client, a scope, an identity assertion, or any Gmail access to the extension. Specification: [`../design/boomerang-extension-auth-proposal.md`](../design/boomerang-extension-auth-proposal.md), sections 6, 8, 9 and 10. Wire surface: [`../design/boomerang-api-contract.md`](../design/boomerang-api-contract.md), sections 3.2, 3.5, 4.1, 5.1 and 5.2. Closes gate `ARCH-B9`. |
| `MIG-16` | **Account scoping is enforced by composite primary keys with composite foreign keys, plus an account-scoped repository boundary the unscoped session cannot escape.** Both mechanisms together, as one change; row-level security is the named follow-on and the ORM query filter is rejected. Accepted 2026-09-13. | Add `account_id` as the leading primary-key column on `order_items`, `return_policies`, `policy_rules` and `return_summaries`; make every child foreign key composite, explicitly `NOT DEFERRABLE` and `MATCH FULL`; keep `orders.id` a single-column, globally unique primary key and assert that in a test, because account isolation now rests on it. Route and service code takes the scoped repository and never a session or `select`. Resolves the low-level design review's `DAL-2`. Specification: [`../design/boomerang-account-scoping.md`](../design/boomerang-account-scoping.md), sections 3, 5, 5.1, 5.2 and 9. Its load-bearing claims were verified by execution against SQLAlchemy 2.0.52 and PostgreSQL 17.11. |
| `MIG-17` | **The v1 extension-authentication posture closes the four defects that blocked the pairing-lifecycle ticket: no decline route, no same-browser correlator, no credential tombstone, and an accepted sign-out stranding residual.** The pairing lifecycle is built from `pairing_requests`, `auth_grants` and `auth_credentials` only. Pairing status is `pending`, `approved`, `redeemed`; `rejected` is not added, because no route can reach it and a pairing can be approved only by the signed-in user themselves, so an undeclined pairing is harmless and expires on its own. No correlator cookie and no correlator column on either record. Account deletion writes no tombstone, so a later call answers `not_linked` and the extension selects its terminal cleanup on whether it presented a credential — a fact it holds locally and the server cannot recover. Accepted 2026-09-13. | Drop `rejected` from the pairing status enum and its check-constraint branch; drop `approval_correlator_hash`, `browser_correlator_hash` and `ix_auth_grants_account_id_correlator`; narrow `auth_grants.revoked_reason` to `user_disconnected`, `dashboard_sign_out` and `refresh_reuse`; do not build `revoked_credentials`. `account_deleted` stays in the published `details.auth_reason` enum as reserved and unreachable in v1, because removing a value from a closed set is the breaking change. The approval copy says *close this page*, not *decline*. The sign-out stranding residual stays inside `ARCH-B1` and is mitigated only by a dashboard sign-out warning composed from the existing `in_progress_count`. Specification: [`../design/boomerang-auth-open-decisions.md`](../design/boomerang-auth-open-decisions.md), sections 2 and 5. Requires the contract and proposal amendments listed in that document's section 7. |
| `MIG-18` | **Two standing constraints on the extension are confirmed rather than left as accidents of the authentication decision.** Linking through the dashboard is a precondition for every extension capability: an unlinked extension may show its popup and offer to link, and may not read a retailer page, start a run, publish a summary, or buffer or queue page content against a future credential. The browser-identity permission is not added to the manifest in v1, and changing that reopens `ARCH-B9` rather than arriving inside an implementation ticket. Accepted 2026-09-13. | The popup's pre-link state is the explainer and the link offer and nothing else. The manifest stays `activeTab`, `scripting` and `storage`, unchanged, as `MIG-09` already requires. The repo-wide guardrails gain a rule that the extension has no Google relationship, gains no identity permission, never puts the credential in synced storage, and never lets a content script touch the credential or the network. Closes section 13 items 3 and 6 of [`../design/boomerang-extension-auth-proposal.md`](../design/boomerang-extension-auth-proposal.md). |
| `MIG-19` | **Dashboard sign-out revokes every live extension grant on the account, in every linked browser — not only the browser being signed out from.** This is the user's answer to the one genuinely open product question in the authentication surface, and it amends the *scope clause* of the sign-out behaviour decided under `MIG-15` earlier the same day; that decision's substance, that sign-out revokes, stands unchanged. Per-browser scoping was rejected because it cannot be made reliable. Recognising “the same browser” requires a durable per-browser marker, and in several entirely ordinary situations — cookies cleared, a private window, a sign-out from a different machine, a fresh profile — the marker is absent and **nothing is revoked at all**: the user believes they are signed out while the extension in that browser keeps working. It fails silently, and in the direction the user explicitly did not want. Account-wide revocation has no quiet failure mode and stores no new per-browser identifier. Accepted 2026-09-13. | No schema change, no route change and no contract change. The scope lives behind the single service-layer seam `revoke_grants_for_sign_out(account_id)` already required by `MIG-17`, which defaults to account-wide, so **this answer is implemented by the default** and the seam simply stops being provisional. **No correlator ships, in any form, and that is now permanent rather than provisional** — the two nullable columns, the correlator cookie and the seam predicate that `PROV-05` held open are declined outright, not deferred. Two costs widen and are recorded here rather than discovered later. Re-pairing friction now applies across every linked browser: one sign-out anywhere unlinks all of them and each costs a fresh one-time approval. And the `ARCH-B1` sign-out stranding residual widens with it — unlinking a browser ends any half-finished return in it, those returns cannot be resumed because the `ARCH-B1` reset needs a live grant, and they go back to `not_started` — which now happens in every linked browser at once rather than in one. The mitigation is unchanged and adds no architecture: the dashboard's sign-out confirmation warns when `in_progress_count` is non-zero. Resolves `PROV-05` and closes the revocation-scope question tracked under `ARCH-B9`. Amendments made: [`../design/boomerang-extension-auth-proposal.md`](../design/boomerang-extension-auth-proposal.md) sections 10 and 13 item 1, and [`../design/boomerang-api-contract.md`](../design/boomerang-api-contract.md) sections 5.1 and 15. |
| `MIG-20` | **`details.auth_reason` of `credential_expired` is an extension-only value, and the dashboard leg has no refresh path at all.** An earlier revision of the wire contract told every client that received the value to refresh once and retry once. A dashboard principal cannot do that: `POST /v1/auth/refresh` requires an extension principal in as many words, and the contract defines no other refresh route for any leg, so the instruction told one of the two principals to perform an operation the same contract forbids it. The alternative — giving the dashboard a refresh mechanism of its own — was rejected because it invents a route, a schema and a wire surface at the end of the design, to serve a state that need never arise. What arises instead is the constraint recorded in the consequence column: with no refresh on the dashboard leg, a dashboard access credential that outlives nothing is pointless, so its lifetime *is* its grant's lifetime, and the "credential expired, grant still live" row of the resolution order has no dashboard instance to describe. That row is therefore left exactly as written and stays normative; it is vacuous for the dashboard principal rather than wrong, and the resolution order in [`../design/boomerang-auth-open-decisions.md`](../design/boomerang-auth-open-decisions.md) section 5.3 gains no case and loses none. Accepted 2026-09-13. | No route, no schema and no wire change: `details.auth_reason` keeps all five published values, and `credential_expired` is not removed from the closed enum — it is documented as reachable by one principal only. The dashboard's recovery from any `401` is a fresh credential exchange through `POST /v1/auth/google`, which mints a new dashboard grant rather than reviving the old one; that is correctness-neutral because `GET /v1/auth/grants` is extension-kind only and expiry is always evaluated at read time. One configuration constraint becomes load-bearing and belongs with the other authentication numbers under `ARCH-B4`: **a dashboard access credential's lifetime must equal its grant's lifetime**, enforced by a startup configuration check rather than by a reviewer's memory, exactly as the `last_used_at` coarsening interval is. Two contract tests carry the claim: no response to a dashboard principal ever carries `credential_expired`, and a configuration that violates the lifetime equality fails validation rather than starting. The same amendment fixed two further rows of the same table that gave extension-shaped instructions to both principals — `grant_revoked` told every client to clear its credential and local workflow records, and `not_linked` told every client to offer the linking flow; the dashboard has no local records, cannot clear its own `HttpOnly` cookie, and has no linking flow — so the whole table now states which principals can receive each value and what each is required to do. Amendments made: [`../design/boomerang-api-contract.md`](../design/boomerang-api-contract.md) sections 2, 4.1, 5.2, 13 and 14. |
| `MIG-21` | **The double-submit token on `DELETE /v1/account` is withdrawn; strict `Origin` matching plus `SameSite=Lax` is the whole of the dashboard's forgery defence, on that route as on every other mutating one.** The requirement could not be implemented from the accepted documents: no document ever named the token, gave its cookie attributes, said where it was issued, or said how it was compared. Specifying it concretely was rejected on the merits rather than for cost. A double-submit token must be readable by page script, which means a second cookie *without* `HttpOnly`, which trades away the one property the session posture is built on; and it is the weaker control in any case, because `Origin` is set by the browser and cannot be written by script, while double-submit falls to an attacker who can write a cookie anywhere on the registrable domain — and this design's `SameSite=Lax` posture *requires* the dashboard origin and the API origin to share a registrable domain, which is precisely the configuration in which a sibling host makes double-submit weakest. Accepted 2026-09-13. | No route, no schema and no wire change, and nothing a client relies on narrows: no client ever sent such a token, because no document ever defined one to send. `DELETE /v1/account` keeps every other control it had — it requires a dashboard principal, so a stolen extension credential cannot reach it, which is where the irreversibility of deletion is actually answered — and it is refused outright when `Origin` is absent or mismatched, as every mutating dashboard route is. One contract test asserts the removal rather than assuming it: the route is refused on an absent or mismatched `Origin`, and accepted on a matching one with no forgery token of any kind presented. If a later deployment cannot put the dashboard and the API on one registrable domain, this decision is reopened together with the `SameSite=Lax` precondition it shares that dependency with, and not before. Amendments made: [`../design/boomerang-api-contract.md`](../design/boomerang-api-contract.md) sections 2, 3.5 and 14, and [`../design/boomerang-extension-auth-proposal.md`](../design/boomerang-extension-auth-proposal.md) section 8's dashboard-leg bullets and posture table. |

#### MIG-14 — Separate authored milestones from the generated task plan

[`boomerang-milestones.md`](boomerang-milestones.md) is the human-authored, authoritative
milestone/workstream plan. [`boomerang-plan.md`](boomerang-plan.md) is reserved for a future
generated task-level plan and index and currently contains only a compatibility placeholder.

A later implementation pass will refactor the generator to combine the milestone source with an
approved, reconciled task corpus. That generated artifact may report task status, traceability, and
dependency analysis, but tasks and their derived output must never redefine scope, priorities,
milestones, or architecture. The existing task corpus and planning scripts remain historical until
that pass. No repository hook or CI workflow currently enforces those scripts.

### Provisional assumptions and unfrozen implementation choices

| ID | Provisional boundary | What would make it final |
|---|---|---|
| `PROV-01` | Normalization may begin synchronously. | Measurements and the full runtime decision under `ARCH-B2`; asynchronous work is introduced only if those results require it. |
| `PROV-02` | **Resolved 2026-09-13 by `MIG-15`.** Session transport and the Google credential-exchange route are decided and frozen: a first-party cookie on the dashboard leg, a bearer credential on the extension leg, one credential-exchange route called only by the dashboard. The stable v1 bodies did not change. | Nothing further. Retained here as the record of how the boundary closed. |
| `PROV-03` | The logical data contract is sufficient for schema exploration, repositories, and frontend fixtures. **Narrowed 2026-09-13 by `MIG-16`**, which fixes the account-scoping key, constraint and index decisions now rather than after `ARCH-B4`. | Select the remaining database/ORM, migration-tooling and lifecycle behavior consistently with `ARCH-B4`. Migration tooling does not yet exist in this repository at all, which `MIG-16` makes urgent rather than optional. |
| `PROV-04` | Existing client, server, Compose, and infrastructure files may support local development during migration. | A separate deployment decision establishes the target compute, database, network, hosting, secret, environment, and pipeline topology. |
| `PROV-05` | **Resolved 2026-09-13 by `MIG-19`.** Dashboard sign-out revokes every extension grant on the account, behind one named service-layer revocation seam and nowhere else. This was recorded here as the interim default while the revocation-scope question was with the user; the user chose account-wide, so the default became the decision and this boundary closed as written rather than by being changed. | Nothing further. Retained here as the record of how the boundary closed. The same-browser alternative it held open — two nullable columns, one correlator cookie and one predicate inside the existing seam — is now declined permanently rather than merely unbuilt. The note that this scope widens the `ARCH-B1` sign-out stranding residual still holds, and is now a standing consequence recorded under `MIG-19` rather than a caveat on a provisional default. |
| `PROV-06` | **No cap on how many browsers one account may link.** No uniqueness constraint is written on `auth_grants` beyond `uq_auth_grants_id`. | A product decision on a cap, which must be taken together with the grant expiry semantics because counting *live* grants means evaluating both expiries. Both behaviours at a cap are user-visible — refusing a legitimate third machine, or silently evicting a browser the user did not touch — which is why neither is chosen here. The control that already exists is the linked-browsers list, which makes every grant visible and revocable. |
| `PROV-07` | **The approval screen shows the closed-vocabulary browser label and the request time, and no location.** Both facts are already stored for the linked-browsers list, so nothing new is collected about the user and the privacy copy gains no new claim. | The privacy-copy pass. Adding an approximate location would be a new collection and a new dependency and is a product call; it is not taken here. The label is not a phishing control — it originates with the extension, so an attacker declares a plausible one — and must not be presented as one; the short-code comparison and the absence of any code-entry path are the controls at approval time. |
| `PROV-08` | **No authentication number is invented anywhere in code or schema.** Access and refresh credential lifetimes, grant idle and absolute limits, pairing lifetime, the refresh rotation grace window, the `last_used_at` coarsening interval and every rate-limit ceiling are configuration values with no defaults. | `ARCH-B4`. The shapes are architectural and hold whatever the numbers turn out to be. Two cross-constraints must be enforced by a configuration check rather than by review. The coarsening interval must be far smaller than the idle limit, or the idle limit is evaluated against a stale `last_used_at` and grants outlive it. And **a dashboard access credential's lifetime must equal its grant's lifetime** — added 2026-09-13 by `MIG-20`, because the dashboard leg has no refresh path, so a shorter-lived dashboard credential would end a live session with no way to continue it. A configuration violating either fails validation rather than starting. |

None of these provisional boundaries authorizes invented payload ceilings, latency budgets, retry
rules, retention windows, bridge credentials, or production resources.

### Deferred capabilities

| Capability | Current disposition |
|---|---|
| Google Calendar | Priority 2; separate incremental consent; detailed design waits for `ARCH-B5` |
| Carrier pickup | Deferred from v1 for every carrier, including USPS, UPS, FedEx, retailer pickup, and paid pickup |
| Stop/Continue and interrupted-run resumption | Deferred; exact conservative v1 interruption acceptance remains `ARCH-B1` |
| QR or label artifact storage | Deferred; v1 stores only outcome status |
| Asynchronous normalization | Deferred unless `ARCH-B2` measurements require it |
| Gmail and unattended retailer access | Excluded, not queued as later v1 work |
| Cross-browser support | Deferred; Chrome only for v1 |
| Automatic extension linking on a dashboard visit | Deferred; an intentional follow-on once `ARCH-B6` closes, not a gap. It is a user-experience layer over an authentication design that already works, and it would reuse the pairing records `MIG-17` builds |

### Open architecture decisions

These entries record planning gates, not placeholder answers.

| Gate | Open decision | Planning effect |
|---|---|---|
| `ARCH-B1` | Exact v1 behavior after user, tab, page, or worker interruption. **One sub-decision inside this gate is closed:** the terminal disposition of an in-progress summary whose run ends without an outcome, decided 2026-09-13 and recorded immediately below | Blocks final interruption behavior and acceptance; does not turn checkpoints into resume support. The closed sub-decision unblocks the summary transition table and nothing else |
| `ARCH-B2` | AI payloads, observation binding, latency, timeout, retry, sync/async, and hosting fit | Blocks final normalization and per-step agent contracts and runtime acceptance |
| `ARCH-B3` | Allowed evidence and publisher for `handed_to_carrier` | Blocks handoff writes; defensive reads remain allowed |
| `ARCH-B4` | Record/checkpoint/token lifetimes, single-order deletion, cleanup, backup, recovery, and expiry | Blocks detailed lifecycle behavior beyond baseline account deletion and local clearing |
| `ARCH-B5` | Calendar component ownership, wire contract, scope, token custody, refresh/revocation, and updates | Blocks priority-2 Calendar implementation |
| `ARCH-B6` | Secure dashboard-to-extension binding, addressing, transport, acknowledgements, and revocation. **Extension-to-server authentication is not part of this gate**; it is `ARCH-B9`, decided separately and first | Blocks live connection and dashboard start/focus integration. Does not block ingestion or summary publication, which authenticate under `MIG-15` |
| `ARCH-B7` | First retailer | Blocks adapters, retailer fixtures, policy assumptions, rescan rules, and real-browser acceptance |
| `ARCH-B8` | Meaning, evidence, and legal transitions for `complete` | Blocks `complete` writes independently of carrier handoff |

#### `ARCH-B1` sub-decision — the abandoned run and the stranded summary

**Decided 2026-09-13.** An in-progress return summary whose run ends without an outcome leaves that
state through a validated extension-published reset to `not_started`, and through nothing else.

This is recorded here, inside the interruption gate, because that is where it belongs and because it
had no owner anywhere else. The high-level design review's `DATA-4` and the low-level design review's
`TRACE-2` both found the same hole: the interruption rule writes no summary on the way out, the
page-diverged rule writes no summary on the way out, and the transition policy was deferred to three
gates — the interruption gate, scoped to browser behavior; the retention gate, scoped to lifetimes;
and the handoff and complete gates, scoped to states an abandoned item never reaches. Each gate
disclaimed the case. `TRACE-2` recommended folding it into this gate as an explicit sub-decision so
it could not fall between them again, and recommended the reset shape as the cheapest that fits the
existing contract: one new row in the transition table and one relaxation of the rule that
`not_started` is server-created only. The alternatives it costed — ageing an in-progress summary out
of the metrics after a fixed interval, or a user-initiated reset from the dashboard — need the
retention gate and a new wire route respectively.

What it is, precisely:

- **Not a new route.** It is the existing `PUT /v1/items/{item_id}/return-summary` with `state` of
  `not_started` and `update_source` of `user_confirmed`. No new field, no new body shape, no new
  deferred contract, and it inherits the enforceable caller column unchanged: that route already
  requires an extension principal, and a dashboard principal is refused.
- **Guarded, not open.** The server accepts it only from an extension principal, only with
  `user_confirmed` as the source, only when the stored state is `in_progress` compared in the same
  transaction as the write, only with `handoff_evidence` of `null`, and only when `observed_at` is at
  or after the stored `observed_at`. A page observation carrying `extension_live_page` can never
  request `not_started`.
- **Monotonicity is relaxed and bounded, not broken as a principle.** Exactly one backward edge
  exists. No observation can move an item backward from any state, which is what the monotonic rule
  was protecting. The relaxation is confined to an explicit user act, which is the "explicit
  reconciliation rule" the data model's consistency rule already reserved.
- **It destroys nothing.** `not_started` is the state the item would have held had the run never
  started; the summary holds no artifact, no evidence and no history. Combined with account scoping
  and the `in_progress` precondition, a reset is not a data-loss vector.
- **Metrics.** The item leaves `in_progress_count`. `closing_soon_count` is deliberately unchanged:
  abandoning a run does not make the return less due.

The specification is
[`../design/boomerang-api-contract.md`](../design/boomerang-api-contract.md), section 11, which also
states idempotency and the race semantics against a live publication from another tab.

Two things this sub-decision does **not** do, stated so they are not assumed closed with it:

1. It does not reach an abandonment whose trigger is the loss of the extension's grant — dashboard
   sign-out under `MIG-15`, disconnection from the linked-browsers list, or account deletion. A
   revoked extension cannot publish anything, and after re-linking it has already cleared the
   workflow records that would tell it which items were stranded. Those items stay stranded, and
   that residual stays in this gate. **It widened on 2026-09-13 under `MIG-19`**, which is recorded
   here rather than re-registered elsewhere: this item first read “sign-out in the same browser,”
   and sign-out is now account-wide, so one sign-out on any machine strands the in-progress returns
   in *every* linked browser at once rather than in one. The mitigation is unchanged and is a
   dashboard-only one — the sign-out confirmation warns from the existing `in_progress_count`.
2. It does not add the append-only transition record that both reviews recommend. A reset that leaves
   no trace is indistinguishable from a run that never started, and a user disputing a status has
   nothing to appeal to. That remains open under `ARCH-B4`.

A known defect compounds with this case and is **not** fixed here: the committed unique constraint on
orders admits nulls, so a user who recovers by rescanning an order page whose retailer reference was
unreadable creates a second order with fresh `not_started` summaries, and the dashboard shows the
same physical item twice. That is the low-level review's `DAL-3`; it is a schema change, and it is
recorded here only so the interaction is visible.

### Closed architecture decisions

| Gate | Decision it owned | Closed | Closed by |
|---|---|---|---|
| `ARCH-B9` | How the extension obtains, presents, renews and loses an authenticated identity at the API, where that credential lives, and the cross-origin and request-forgery posture of both client legs | 2026-09-13 | `MIG-15` |

`ARCH-B9` did not exist before 2026-09-13, and that is the point of recording it here rather than
quietly writing the decision down somewhere. The low-level design filed extension-to-server
authentication under `ARCH-B6`, which owns how a dashboard addresses an extension — addressing, not
credentials. The low-level design review's `TRACE-1` finding named that mis-filing as the reason the
decision was unowned and invisible to every gate. It is registered now so the record shows both that
it existed and that it is closed.

Two items inside `ARCH-B9`'s subject matter were **not** closed by `MIG-15` and were tracked against
it: the dashboard sign-out route, which no document enumerates, and the browser or session
correlator that scopes sign-out revocation to a single browser, which the accepted design required
and did not specify. **One of the two is now closed and the other has changed shape.** The
correlator item is closed by `MIG-19`, which declines the correlator outright: nothing requires it,
so nothing about it is open. The sign-out route remains open, but only as a wire shape — its
behaviour is decided — and it stays in the wire contract's deferred-contracts table on that basis.

#### `ARCH-B9` — the revocation-scope question, put to the user and **answered** 2026-09-13

> **CLOSED 2026-09-13. The answer is account-wide, registered as `MIG-19`.** The question and the
> argument that produced it are kept below unchanged, because the reasoning is what makes the answer
> reviewable; the resolution is recorded at the end of this subsection.

Of the two items tracked against `ARCH-B9` above, the correlator resolved into a product question that
an engineer must not answer silently, and it is the only one in the whole open authentication surface
that did.

The correlator can be built and it cannot be made reliable. Its failure cases — the cookie absent, the
cookie cleared, a sign-out from another browser, an incognito window — are every one of them a **silent
fail-open**: the user signs out, believes they are signed out, and the extension in that browser keeps
working. That is the exact direction the user's stated mental model, "sign out means signed out," was
protecting. Account-wide revocation needs no correlator, needs no new durable per-browser identifier in
the privacy copy, and has no silent case; it is blunter than what was decided, because signing out on
one machine unlinks the others and each costs a re-approval.

**No correlator ships in v1 either way**, and that part is an engineering call taken under `MIG-17`:
the correlator is the irreversible direction, since it means minting and disclosing a durable
per-browser identifier, while adding one later is a clean additive change. The scope itself is the
user's, because account-wide changes the letter of the section 13 item 1 decision the user took on
2026-09-13 — it satisfies that decision's intent and over-satisfies its scope clause, and the
difference is visible to the user.

`PROV-05` is the interim default and the implementation seam, so **this question blocks nothing in the
pairing lifecycle**. It blocks the sign-out route's wire shape, the privacy copy, and the correlator
columns if they are ever wanted. The question as drafted for the user is section 4 of
[`../design/boomerang-auth-open-decisions.md`](../design/boomerang-auth-open-decisions.md).

**The answer, 2026-09-13: account-wide.** The user chose to revoke every linked browser's grant on
sign-out, and the reason they gave is the one this subsection argued: per-browser scoping cannot be
made reliable, and every way it fails — a cleared cookie, a private window, a sign-out from another
machine, a fresh profile — fails by doing nothing at all while the user believes they are signed
out. They preferred a blunt mechanism that never lies about being signed out to a precise one that
quietly does not run, and they accepted the two costs that come with it: a re-approval in every
linked browser after any sign-out, and a wider `ARCH-B1` stranding residual, since a sign-out now
ends half-finished returns in every browser rather than one and those returns go back to
`not_started`. The decision is registered as `MIG-19`; `PROV-05` is resolved by it, the correlator is
declined permanently, and the sign-out route's wire shape is the only part of this item still open.

### Supersession map for the 2026-08-27/2026-09-01 decisions

The historical `D1`–`D28` entries below remain unchanged as records of the old plan. Their
current disposition is explicit here.

| Old decision | Current status | Migration effect |
|---|---|---|
| `D1` | **Superseded** | A free printable USPS label is no longer the PoC gate. Retailer selection and acceptance are now `ARCH-B7`; QR or label outcome does not require pickup. |
| `D2` | **Superseded in its fixture rule** | Captured raw or bounded sanitized page representations may not become durable fixtures. Retailer fixtures must be designed after `ARCH-B7` under current privacy constraints. |
| `D3` | **Superseded** | USPS access is not a v1 dependency because all carrier pickup is deferred. |
| `D4` | **Partially retained** | Measuring realistic model payloads and latency remains required by `ARCH-B2`; the old timeout constants and batch assignment are not current. |
| `D5` | **Historical only** | Partial gating remains a useful planning principle, but the named batches/tasks are obsolete. |
| `D6` | **Superseded** | The database-backed dashboard is core. Its connection to the extension is not cut; it is blocked explicitly by `ARCH-B6`. |
| `D7` | **Superseded** | The fixed Lambda/no-database topology conflicts with the database-backed architecture. Production topology is open. |
| `D8` | **Superseded with D7** | No current milestone implements the old Lambda target or relies on its legacy-scaffold retirement sequence. |
| `D9` | **Superseded** | The old deployment-track timing and dependency are withdrawn with the obsolete task graph. |
| `D10` | **Retained as a delivery practice** | CI should exist early, but its exact task and sequence await task reconciliation. |
| `D11` | **Superseded** | Batch barriers, 20-task floor, and approximately 35-slot makespan are not valid for the current architecture. |
| `D12` | **Superseded** | USPS mocks and sandbox reconciliation are deferred carrier work, not active v1 tasks. |
| `D13` | **Historical quality target** | The old 95% extension threshold is not affirmed by the current design; the future task pass must set evidence-based gates. |
| `D14` | **Retained as repository practice** | The repo-wide hook convention still applies, but task timing is pending reconciliation. |
| `D15` | **Partially retained** | Shared canonical contract examples remain useful; the old ingestion, next-step, pickup, and error payload set is replaced by the current API/data contracts. |
| `D16` | **Superseded** | The current stable v1 contract does not require `X-Boomerang-Client-Version`. |
| `D17` | **Superseded** | The old configuration surface is not a current contract; new runtime values wait for the relevant design gates. |
| `D18` | **Superseded** | A sweep over obsolete configuration names cannot establish current traceability. Rebuild checks after task reconciliation. |
| `D19` | **Historical only** | The storage-barrel optimization was tied to the old extension-owned data tasks and makes no current sequencing commitment. |
| `D20` | **Not carried forward** | Extension identity/origin requirements must follow `ARCH-B6` and the future deployment design; the old keypair task is not current authority. |
| `D21` | **Superseded** | USPS test-double/runtime-stub design is deferred carrier work. |
| `D22` | **Superseded** | Simulated pickup booking has no core-v1 user surface because pickup is deferred. |
| `D23` | **Partially retained** | Real-browser acceptance remains required, but its scenario now ends in a validated QR/label outcome and excludes pickup and Calendar. |
| `D24` | **Historical only** | Agent count and per-task approval policy cannot be carried forward before a new task graph exists. |
| `D25` | **Accepted and retained** | Correct upstream documents and contracts rather than working around conflicts. |
| `D26` | **Superseded for v1** | Generalizing pickup does not keep it in scope; all carrier pickup is deferred. |
| `D27` | **Superseded** | Preferences are account data in the database using the current four-value vocabulary. Return address/pickup preference is not a v1 preference, and no preference auto-selects a method. |
| `D28` | **Partially retained** | The dashboard remains core, but it reads database APIs rather than extension-local summaries. The bridge/origin protocol remains `ARCH-B6`, not a settled `externally_connectable` contract. |

## Historical plan review — 2026-08-27 and 2026-09-01

> The remainder of this file records the decisions that produced the former batch/task plan. Counts,
> schedules, requirement identifiers, API/configuration names, carrier behavior, and upstream
> amendments below describe that historical plan only. The supersession map above controls their
> current status.

**Date:** 2026-08-27
**Reviewed document:** [`plan/boomerang-plan.md`](boomerang-plan.md) at 79 tasks / 10 batches
**Method:** adversarial interview across six rounds, each finding checked against the repository
rather than against the documents describing it.

This record exists because several of the decisions below are not derivable from the plan, the
designs, or the code — they are choices about scope, sequencing and risk that a reader six weeks
from now would otherwise have to reverse-engineer. Each entry states the defect found, the decision
taken, and the edit it implies. Where a decision contradicts an upstream design document, that is
named explicitly and the amendment is listed.

The plan grows from **79 tasks to 91**, and its honest makespan is restated from a claimed 19 slots
to roughly **35** — the 79-task plan never cost 19 either; 19 was its dependency floor, and the hard
commit barrier at each batch boundary was already being paid without being counted.

**`Dn` in this document is local to this document.** [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
carries an older `D1`–`D7` series of product decisions, and both series are cited in the same
sections of the requirements and the high-level design. Every reference this review introduced
upstream is written as "plan decision `Dn`" for that reason.

---

## Summary of changes

| # | Decision | Touches |
|---|----------|---------|
| D1 | Add a blocking **Batch 0** feasibility spike | plan, HLD Q5/Q6 |
| D2 | Batch 0 exits with scrubbed, committed fixtures | plan |
| D3 | Batch 0 applies for USPS API access on day one | plan |
| D4 | Batch 0 measures Bedrock parse and action latency | plan, HLD Q9 |
| D5 | Batch 0 blocks only retailer-shaped work | plan |
| D6 | **Cut FR-3.6.3** (dashboard → extension messaging) from PoC scope | plan, requirements, HLD Q1/Q8 |
| D7 | Rewrite `infra/` for the Lambda architecture | plan, HLD Q3 |
| D8 | Retire `infra/AGENTS.md`'s "Legacy scaffold" section when I.1 lands | plan, HLD Q3 |
| D9 | Infra runs as a **track opening after Task 6.5**, not a trailing batch | plan |
| D10 | `.github/workflows/ci.yml` lands in **Batch 1** | plan |
| D11 | Keep the batch barriers; restate the schedule honestly | plan |
| D12 | Keep the doc-derived USPS mocks; add a sandbox reconciliation task | plan, HLD Q11 |
| D13 | Extension coverage gate: 95% line + branch over `src/` | plan |
| D14 | Extend `.husky/pre-commit` to the extension workspace | plan |
| D15 | Add a repo-level `contracts/` directory of golden wire payloads | plan |
| D16 | Name the client-version header upstream | plan, requirements §4.1 |
| D17 | Fix three wrong configuration-parameter names; add a missing one | plan |
| D18 | Extend the Task 10.2 sweep to configuration-parameter names | plan |
| D19 | Split the storage barrel; one file per repository | plan |
| D20 | Generate the pinned extension keypairs in Batch 1 | plan, HLD Q4 |
| D21 | Split `MockUspsAdapter` into a scripted double and a runtime stub | plan |
| D22 | Label mock-backed bookings as simulated in the popup | plan, requirements FR-3.4.5b/§5.1 |
| D23 | Add a manual acceptance task after Batch 8 | plan |
| D24 | Two agents; per-task approval on the driver and storage spines | plan |
| D25 | Amend upstream documents rather than working around them | requirements, HLD |
| D26 | Generalize carrier pickup to configured third-party carriers | requirements, HLD, LLD, plan |
| D27 | Add retailer-agnostic onboarding preferences | requirements, HLD, LLD, plan |
| D28 | Reinstate the dashboard with a concrete origin requirement | requirements, HLD, LLD, plan |

---

## A. Feasibility — the risks the plan started without

### D1. Add a blocking Batch 0 feasibility spike

**Defect.** High-level design §11 Q6 names the Amazon printable-label path as the largest open
feasibility risk and says, in the document's own words, *"prototype this before writing anything
else in `extension/`."* The plan has no spike. Task 3.14 builds the PoC retailer adapter against
selectors nobody has looked at, and Task 2.8's fixture harness has no fixtures to harness.

**Decision.** A new **Batch 0** runs before Batch 1 with three go/no-go criteria, checked by hand
against a real logged-in retailer account:

1. A **printable USPS label** is reachable through the return flow without leaving the browser.
2. Each offered return method's **price is readable from the DOM** at the point of choice.
3. The printable label option is **free**.

If any criterion fails, the PoC retargets to a different retailer or a different return method
*before* thirteen tasks are written against an assumption that does not hold. The exit is a written
finding committed to the repository, not a verbal "it works".

**Why it is worth a batch.** The three criteria are exactly the assumptions FR-3.3.4, FR-3.3.5 and
FR-3.4.1 encode. Discovering criterion 3 is false after Batch 7 invalidates the entire pickup
branch — Tasks 4.3–4.5, 5.3, 6.4, 7.4, 7.5, 7.9, 7.10, 8.5 and 9.5.

### D2. Batch 0 exits with scrubbed, committed fixtures

**Decision.** The spike does not just answer yes/no; it captures the DOM subtrees it navigated,
scrubs them per low-level design §9 Q1, and commits them. Those fixtures are the real input to
Task 2.8 and Task 3.14.

**Why.** Task 2.8 currently builds a harness and a scrubbing README for fixtures that do not exist.
A spike that answers the question and throws away the evidence forces the same pages to be
navigated twice.

### D3. Batch 0 applies for USPS API access on day one

**Defect.** Tasks 4.3–4.5 build a USPS OAuth token provider and adapter. Nothing in the plan
obtains USPS API credentials, and that is a third-party approval with no stated turnaround.

**Decision.** Filing the access request is a Batch 0 task. It is the one item in the plan whose
latency is not ours to control, so it starts before anything that depends on it.

### D4. Batch 0 measures Bedrock parse and action latency

**Defect.** High-level design §11 Q9 records model latency as unmeasured, yet `BEDROCK_TIMEOUT_PARSE_MS`
= 9000 and `BEDROCK_TIMEOUT_ACTION_MS` = 4500 are already written into the configuration table, and
NFR-6.4 promises an action round trip under five seconds. Those are guesses with a requirement
resting on them.

**Decision.** Batch 0 times a cold and a warm parse invoke against a subtree captured by D2, and a
warm action invoke, and records the numbers. `server/app/bedrock.py` already implements the client,
per-call-site model resolution and `verify_config()`, so this costs a script, not a subsystem.

**Consequence.** If the measured action latency does not fit NFR-6.4's budget, that is an upstream
amendment (see D25), decided before Batch 5 builds a service against the number.

### D5. Batch 0 blocks only retailer-shaped work

**Decision.** Batch 0 gates Tasks 2.8, 3.13, 3.14, the driver flows that depend on them, and the
Batch 9 driving rows. It does **not** gate the server track, nor Tasks 1.2, 2.4, 2.5, 2.6 or 2.7.

**Why.** A blocking spike that idles both workspaces converts a risk reduction into a schedule loss.
The server's wire contract does not depend on which retailer wins.

---

## B. Scope — what the PoC is not

### D6. Cut FR-3.6.3 entirely

**Defect.** FR-3.6.3 (the dashboard messaging the extension via `externally_connectable`) requires a
dashboard hostname. High-level design §11 Q1 records that hostname as undecided and blocking
packaging — and Task 1.2, the *second task in the plan*, writes the manifest.

**Decision.** Cut the requirement from PoC scope rather than block Batch 1 on a hostname nobody
needs yet. Concretely: no `externally_connectable` key in the manifest, drop the external half of
Task 5.6, drop the Task 9.7 external-messaging row, and declare a **second acknowledged gap**
alongside FR-3.6.2 in the traceability table, allowlisted in the Task 10.2 sweep.

**Consequences.** HLD Q1 is resolved by removal — no hostname is needed for the PoC. `DASHBOARD_ORIGIN`
leaves the configuration surface. `client/` was already out of scope (low-level design §1); this
makes the extension side of that boundary consistent with it.

**Why cut rather than defer.** A requirement that is "deferred" still shows up as unimplemented in
every sweep. A requirement that is *declared out of scope with its gap recorded* is honest and
passes CI. The plan already has this pattern for FR-3.6.2.

### D7. Rewrite `infra/` for the Lambda architecture

**Defect.** Zero of the 79 tasks touch `infra/`. The directory still provisions a VPC, an internet
gateway, an EC2 instance and security groups with local state — the architecture the high-level
design superseded. NFR-6.6 and NFR-6.7 have traceability rows pointing at application tasks that
cannot satisfy them: no application task can create the alarm NFR-6.6 requires.

**Decision.** Delete the VPC/EC2/security-group scaffold. Provision instead: the Lambda function and
its execution role, a Function URL with single-origin CORS, SSM SecureString parameters for
secrets, an `InputTokenCount` CloudWatch alarm, an AWS Budget, and `reserved_concurrent_executions = 5`.

**Why the concurrency cap.** An `AuthType: NONE` Function URL whose only browser-side control is a
forgeable CORS header is one loop away from an unbounded Bedrock bill. The reservation is the
backstop the budget alarm cannot be, because an alarm notifies after the spend.

**Resolves** HLD §11 Q3.

### D8. Retire the "Legacy scaffold" section of `infra/AGENTS.md`

**Correction to an earlier finding.** `infra/AGENTS.md` was rewritten on 2026-08-26 and is *already*
accurate: it documents the Lambda target state in full, and quarantines the stale VPC/EC2 rules
(`allowed_cidr`, the two-availability-zone floor, `instance_type` replacement) inside a clearly
labelled **"Legacy scaffold"** section that ends with its own instruction — *"When the Lambda
resources land, delete this section along with the VPC, EC2, security group and the `vpc_cidr`,
`instance_type` and `allowed_cidr` variables."* The document is not misleading; it is waiting.

**Decision.** Task I.1 executes that instruction as part of its own definition of done. There is no
rewrite to do — the target state, the sizing table, the "no VPC" rationale, the `reserved_concurrent_executions`
reasoning and the Bedrock-invocation-logging ban are already written and are the specification I.1
implements against.

**Worth noting:** the document also independently confirms two decisions reached in this review —
that infra is *"not on the PoC critical path"* (D9), and that dev and prod are separate extension IDs
with *"one pinned key each"* (D20).

### D9. Infra runs as a track opening after Task 6.5

**Decision.** Not a trailing Batch 11. The infra track opens the moment Task 6.5 exports the Mangum
handler, and runs in parallel with Batches 7–10.

**Why.** Task 6.5 is the last thing infra actually needs — after it, there is a deployable artifact.
Running infra as a trailing batch would idle it through four batches for no dependency reason, and
would push the first real deployment to the end of the project, which is exactly where deployment
surprises are most expensive.

### D10. CI lands in Batch 1

**Defect.** Batch 10's commit checkpoint reads *"CI enforces what review would otherwise have to."*
There is no `.github/` directory and no task creates one. Three tasks write checks that never run.

**Decision.** `.github/workflows/ci.yml` is a **Batch 1** task, written generically to discover both
workspaces: server `make check`, extension build/test/lint, and `scripts/citation-sweep.sh` once it
exists.

**Why Batch 1 rather than Batch 10.** A gate added at the end tells you the last commit was clean.
A gate added at the start tells you which commit broke it. Batch 10's tasks then *add checks to an
existing pipeline* rather than inventing one.

---

## C. Schedule and verification honesty

### D11. Keep the batch barriers; restate the schedule

**Defect.** The plan claims a 19-task critical path and simultaneously mandates that *all* tasks in
a batch complete before the next batch starts. Under a hard barrier the makespan is the sum of the
per-batch poles, not the longest chain — roughly **1 + 2 + 5 + 7 + 2 + 5 + 4 + 5 + 2 + 1 = 34 slots**.
The published chain also omits Tasks 4.8 and 4.10–4.12, which sit on it.

**Decision.** Keep the barriers — they are what makes each commit checkpoint meaningful — and restate
the Critical Path and Parallelization sections in terms of both numbers, naming the barrier as the
reason for the gap, with a per-batch pole table so the arithmetic is checkable rather than asserted.

**The figures as applied.** The 34 above is the *pre-review* plan's cost. After the edits in this
record the numbers move in both directions and land at **~35 slots against a 20-task floor**: Batch 0
adds 2 and the manual acceptance gate (D23) adds 1 to Batch 8 and 1 to the floor; the storage split
(D19) takes Batch 4's pole from 7 down to 4; the deployment track (D9) adds 0, because it runs
concurrently with Batches 7–9 and gates nothing in them. The corrected speedup claim is **~2.6x**
under the barrier, against a 4.5x ceiling the barrier makes unreachable — not the ~4x the plan
advertised.

**Why keep the barriers.** They are the mechanism that keeps a multi-agent run from producing a
repository that is green nowhere. The fix is to stop advertising a number the barriers forbid.

### D12. Keep the doc-derived USPS mocks; add a sandbox reconciliation task

**Defect.** Tasks 4.3–4.5 build the USPS client against `respx` mocks written from documentation.
Nobody has seen a real USPS response. High-level design §11 Q11 asks what USPS does on a duplicate
booking and has no answer.

**Decision.** Keep 4.3–4.5 as they are — waiting on credentials would serialize the whole server
track behind a third party. Add a **"reconcile `UspsAdapter` against the sandbox"** task in the infra
track, which also answers Q11 empirically.

**Why this shape.** It separates "build against the documented contract" from "verify the contract is
real", and puts the second where credentials actually exist.

**Resolves** HLD §11 Q11.

### D13. Extension coverage gate: 95% line and branch over `src/`

**Defect.** The server has `fail_under = 95` with `branch = true`. The extension has no stated
coverage gate at all, and the plan's most intricate logic — the driver state machine — lives there.

**Decision.** 95% line and branch across `extension/src/`. `entrypoints/` is excluded by an
**explicit named list**, not a glob, and is covered by the Batch 9 integration rows instead.

**Why a named list.** A glob exclusion silently swallows anything later dropped into the directory.
A named list makes each exclusion a reviewable line.

### D14. Extend `.husky/pre-commit` to the extension

**Defect.** The hook is server-only. Every extension task in the plan can be committed without
running a test.

**Decision.** Extend the hook to the extension workspace in the same task as D13.

### D15. Add a repo-level `contracts/` directory

**Defect.** The plan's preamble states the wire types are *"a duplicated type by design"*. Nothing in
79 tasks verifies the two copies agree. Both suites can be green on mutually incompatible shapes —
the server's Pydantic model and the extension's TypeScript interface never meet in a test.

**Decision.** A new Batch 3 task creates `contracts/`: canonical request and response JSON for each
of the seven endpoints, plus one error body per reason code. Both suites assert their own
serialization against those files.

**Why golden files rather than codegen.** Codegen would couple the two workspaces' builds and destroy
the Batch 1–7 parallelism that is the plan's main asset. Golden JSON is a shared *artifact*, not a
shared *build step*: each side reads it independently, and a divergence fails a test on whichever
side drifted.

---

## D. Correctness of the plan's own text

### D16. Name the client-version header upstream

**Defect.** Task 3.8 builds a client version gate and Task 4.13 builds the client that must satisfy
it. Neither names the header. Requirements §4.2 specifies that an *absent* header raises
`client-too-old` — so two independently-written tasks that pick different spellings produce a
system where every request from the real client is rejected, and both suites pass.

**Decision.** Name it upstream in requirements §4.1 as **`X-Boomerang-Client-Version`**; cite it from
Tasks 3.8 and 4.13; include it in the D15 golden payloads.

### D17. Fix three configuration names; add a missing one

**Defect.** Tasks 2.5, 3.9 and 4.13 use `PAYLOAD_CEILING_BYTES` and `API_TIMEOUT_MS`. Neither string
appears anywhere in the requirements or the low-level design. The real names are `MAX_INGEST_BYTES`
and `API_REQUEST_TIMEOUT_MS`. `API_RETRY_BUDGET_MS` is specified upstream and absent from the plan
entirely, so the retry budget it governs would not have been built.

**Decision.** Correct both names and add the missing parameter to Task 2.5's constant set and
Task 4.13's client.

### D18. Extend the Task 10.2 sweep to configuration-parameter names

**Decision.** The citation sweep checks `FR-`/`NFR-` identifiers. Extend it to configuration-parameter
names drawn from requirements §5.1/§5.2.

**Why.** D17 is a class of defect, not an instance. An identifier sweep catches a missing requirement
citation but not an invented constant, and the invented constant is the one that compiles.

### D19. Split the storage barrel

**Defect.** Batch 4's seven-task storage chain (4.6 → 4.12) is fully serialized. The plan justifies
this as protecting *"one state machine, one serialising queue"* — but the actual serializing
constraint is that all seven tasks edit `src/storage/index.ts`, a barrel file. That is a scheduling
artifact wearing an invariant's clothes.

**Decision.** One file per repository — `OrderRepository`, `ReturnRepository`, `PickupRepository`,
`AddressRepository`/`SessionStore`. `src/storage/index.ts` is written **once**, in Task 4.6, listing
the exports up front. `StorageCoordinator.transact` stays whole in 4.7 — *that* is a real invariant.

**Effect.** Batch 4's pole drops from 7 slots to ~4, which is the single largest schedule improvement
available in the plan.

---

## E. Gaps found in the tail

### D20. Generate the pinned extension keypairs in Batch 1

**Defect.** No task in 3,223 lines generates the extension keypair or writes the manifest `key`.
FR-3.7.1 requires it. Requirements line 761 explains why: without a pinned key, Chrome derives the
extension ID from the load path, so the ID differs between every machine. NFR-6.5 allowlists exactly
one `chrome-extension://` origin on the Function URL — a literal string that must be known at
`terraform apply` time. Task 10.1 scans the production bundle for a *dev* key, implying two keypairs
that nothing creates.

**Decision.** A Batch 1 task alongside 1.2 generates the dev and prod keypairs. The dev public key
goes in `wxt.config.ts`; private keys go to SSM at `/boomerang/release/<env>/extension-key` per HLD
§8.4, with the prod key additionally held offline. Neither private key enters the repository.

**Why Batch 1 and not the infra track.** The derived origin is an *input* to the CORS policy — it has
to exist before the thing that allowlists it. Batch 1 also makes the ID stable for every unpacked
load from that point on.

**Both keys are required, not speculative.** `infra/AGENTS.md` specifies two environments sharing
nothing, with *"separate CORS origins (they are separate extension IDs — one pinned key each)"*. The
prod key is therefore mandated by the deployment topology independently of whether Boomerang ever
self-packages a CRX, and Task 10.1's dev-key scan is what keeps the two from being confused.

### D21. Split `MockUspsAdapter` into a scripted double and a runtime stub

**Defect.** Task 4.5 designs `MockUspsAdapter` as a strict test double: `push(method, outcome)` queues
per-method outcomes, an **unqueued call is an error** rather than a happy path, and `assert_drained()`
fails on leftovers. But requirements §5.1 makes `CARRIER_ADAPTER=mock` the *runtime* default until
USPS access lands, and D23's acceptance test books against it. A push/pop double cannot serve a
running deployment — the first real request pops an empty queue and raises.

**Decision.** Rename Task 4.5's class to **`ScriptedUspsAdapter`** — same behaviour, honest name,
tests only. Add a task building **`MockCarrierAdapter`** for `CARRIER_ADAPTER=mock`: deterministic
confirmation numbers, a next-available scheduled date, eligible everywhere **except one designated
unserviceable postcode**.

**Why the unserviceable postcode.** FR-3.4.2's graceful second answer is the hardest copy in the
product to get right and the easiest to never see. A designated failing postcode makes it
demonstrable by hand.

**Rejected alternative.** Giving one class a permissive default mode reintroduces exactly the silent
happy-path behaviour Task 4.5 step 3 exists to forbid, one constructor argument away from a test.

### D22. Label mock-backed bookings as simulated

**Defect.** Under `CARRIER_ADAPTER=mock` the extension stores a fabricated confirmation number, writes
an NFR-6.2 `ConsentStamp` for a pickup that was never booked, and the popup renders it as a
confirmed USPS collection. Requirements §5.1 names this failure — *"a production deployment that
silently degrades to a mock returns fabricated confirmation numbers to real users"* — but only
guards production, and the demo runs on the mock by design.

**Decision.** `MockCarrierAdapter` returns confirmation numbers carrying a fixed recognisable prefix.
The popup renders any booking carrying that prefix with a **"simulated — no carrier was contacted"**
label, asserted in a test.

**Why.** The product's own governing rule is that a derived thing is never presented as authoritative.
The one screen showing a confirmation number is the screen most likely to be demonstrated to other
people, and it would be the only screen making a false claim.

---

## F. Execution

### D23. Manual acceptance task after Batch 8

**Defect.** Nothing in the plan runs the built extension in a real browser. Batch 9 drives an
assembled extension under `vitest` against a fake `chrome`; Task 10.1 inspects a bundle statically.
The fake browser is a model of Chrome written by the same people writing the code it validates.

**Decision.** A manual acceptance task after Batch 8, with a written step list and an expected
observation at each step: load `.output/chrome-mv3` unpacked, scan a real order page, drive to the
label choice, confirm, affirm print, book against the mock carrier, open the calendar template,
cancel.

**Why written steps rather than "try it".** An unwritten manual test is not repeatable and its
failure is not reportable. The step list is also the demo script.

### D24. Two agents; per-task approval on the driver and storage spines

**Decision.** One agent on the extension spine, one on the server, both executing through
`implement-task-code`. **Per-task human approval** on driver and storage tasks; **batch-level
approval** on leaf modules.

**Why the split.** The driver state machine and the storage coordinator are where a plausible-looking
wrong implementation is most expensive to discover late — they are the plan's serial spine, so a
defect there invalidates everything downstream. Leaf modules are individually cheap to re-do.

### D25. Amend upstream documents rather than working around them

**Decision.** Where this review found the requirements or the high-level design wrong or incomplete
(D6, D16, D22, and D4 if measurement contradicts NFR-6.4), amend those documents and have the plan
cite the amended text.

**Precedent.** Low-level design §10 already records five upstream amendments it made during review.
The repository's established position is that upstream wins — *and that upstream can be wrong*, in
which case it is corrected rather than routed around. A plan that silently contradicts its
requirements produces a system nobody can audit against either document.

### D26. Generalize carrier pickup to configured third-party carriers

**Defect.** The Amazon return-flow spike found that USPS is not offered consistently: the available
return methods depend on the retailer, item, account, and return context. Naming USPS as the only
pickup carrier would make the implementation specific to one retailer and would reject otherwise
valid carrier-backed return paths.

**Decision.** Use the generic concept **third-party pickup** in the requirements and user-facing
flow. The server supports a configured set of pickup carriers, and `label_carrier` must belong to
that set before eligibility or scheduling can occur. The implementation may support USPS, UPS,
and additional carriers independently; it must not assume one carrier is always available. Amazon's
own door-pickup option is a retailer-provided option and is handled by the retailer adapter unless
an explicit supported integration is added later.

### D27. Add retailer-agnostic onboarding preferences

**Defect.** Return-method choices and form requirements differ between retailers and even between
items or accounts. Without preferences captured before the driver starts, the extension cannot
make a useful first recommendation or know whether a printed label is practical for the user.

**Decision.** On first interaction, offer a skippable onboarding form that stores a return address,
the user's preferred return mode (self-service drop-off or home pickup), and whether the user has
access to a printer. Store these values in a client-only `PREFERENCES` singleton in
`chrome.storage.local`; do not create a server-side user database or account. Preferences guide
which available option is highlighted, but never silently select an option or override the retailer's
actual choices. When the user has no printer, prefer a no-printer-required option such as a QR-code
drop-off when one is available.

### D28. Reinstate the dashboard with a concrete origin requirement

**Defect.** The dashboard was previously cut because its production origin was undecided, but the
product now requires a main dashboard showing returnable value, savings, and ranked return windows.

**Decision.** Reinstate the dashboard requirement and its `externally_connectable` integration.
`DASHBOARD_ORIGIN` defaults to `http://localhost:3000` for development and must be set to a concrete
production origin before a release build; an unset production value fails the build. The dashboard
reads an enumerated summary from the extension: currently returnable value, saved value from
successful returns, and each open item's days remaining in urgency order. These figures are derived
at render time from stored order and return entities, not persisted as running totals. The dashboard
does not receive onboarding preferences.

---

## Upstream amendments required

| Document | Section | Amendment | Decision |
|----------|---------|-----------|----------|
| `boomerang-plan.md` | Header, preamble, Batch 0–10, deployment track, all tail sections | Applied 2026-08-27 | D1–D25 |
| `boomerang-requirements.md` | Overview | Revision banner; `Dn` disambiguated from the `docs/ARCHITECTURE.md` series | D25 |
| `boomerang-requirements.md` | §4.1 | Name the client-version header `X-Boomerang-Client-Version`, normatively, including the rule that a differently-worded header is treated as absent | D16 |
| `boomerang-requirements.md` | FR-3.4.5b | **New requirement:** a booking made without contacting a carrier SHALL disclose itself, detected by confirmation-number prefix rather than by build environment | D22 |
| `boomerang-requirements.md` | FR-3.6.3 | Mark out of PoC scope with rationale | D6 |
| `boomerang-requirements.md` | §5.1/§5.2 | `MOCK_CONFIRMATION_PREFIX` added to the server table; `DASHBOARD_ORIGIN` struck from the extension table with a restore note | D6, D22 |
| `boomerang-high-level-design.md` | §11 Q1 | Resolved by removal — no dashboard hostname needed | D6 |
| `boomerang-high-level-design.md` | §11 preamble | Struck-through vs. **assigned** distinction stated; `Dn` disambiguated | D25 |
| `boomerang-high-level-design.md` | §11 Q3 | Resolved — `infra/` becomes the Lambda topology; the claim that `infra/AGENTS.md` is contradictory is retracted | D7, D8 |
| `boomerang-high-level-design.md` | §11 Q4 | Answered question now also assigned to Task 1.4 | D20 |
| `boomerang-high-level-design.md` | §11 Q5 | Assigned — Task 0.1's second go/no-go criterion | D1 |
| `boomerang-high-level-design.md` | §11 Q8 | Moot for the PoC — no `externally_connectable` to review | D6 |
| `boomerang-high-level-design.md` | §11 Q6 | Resolved — Batch 0 spike, with go/no-go criteria | D1 |
| `boomerang-high-level-design.md` | §11 Q9 | Resolved — Batch 0 measures it | D4 |
| `boomerang-high-level-design.md` | §11 Q11 | Assigned — Task I.3 answers it against the sandbox | D12 |
| `boomerang-requirements.md` | FR-3.3.5, FR-3.4 | Generalize USPS-specific pickup rules to configured third-party pickup carriers | D26 |
| `boomerang-requirements.md` | §3.0 | Add retailer-agnostic onboarding preferences and client-only storage | D27 |
| `boomerang-requirements.md` | FR-3.6.3 | Reinstate the dashboard with render-time return and savings summaries | D28 |
| `boomerang-high-level-design.md` | §4.2, §5.1, §6.7 | Add `PREFERENCES`, onboarding, and dashboard flows | D27, D28 |
| `boomerang-low-level-design.md` | Storage, dashboard messaging, configuration | Add preferences storage and dashboard contract | D27, D28 |

**D1–D25 were applied on 2026-08-27; D26–D28 were applied on 2026-09-01.** Questions 2, 7 and 10 in §11 remain open and
unassigned, and are marked as such rather than quietly dropped: the unauthenticated-endpoint
availability gap, the terms-of-service assessment, and the region choice. None of them blocks Batch
0.

---

## Defects found and not separately decided

Recorded so the traceability edits below are not mistaken for cosmetic:

- NFR-6.6 and NFR-6.7 traceability rows point at application tasks that cannot satisfy them. Fixed by
  D7's infra tasks.
- The published critical path omits Tasks 4.8 and 4.10–4.12, which lie on it. Fixed by D11.
- Task 10.1 scans for a dev extension key that, before D20, nothing created.
