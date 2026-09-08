# Boomerang — Requirements

> **Status:** Rewritten for the product direction approved on 2026-09-05.
>
> The files in [`../docs/`](../docs/) are the source of truth for this document. In particular,
> [`SKETCH.md`](../docs/SKETCH.md) owns product scope and priorities,
> [`RETURN_WORKFLOW.md`](../docs/RETURN_WORKFLOW.md) owns return behavior and state ownership, and
> [`ARCHITECTURE.md`](../docs/ARCHITECTURE.md) owns technical decisions and open blockers. This
> document translates those decisions into testable requirements; it does not supersede them.
>
> The milestone plan has been reconciled with this direction. The task files under `plan/tasks/`,
> implementation, and workspace guidance still describe the older local-only, USPS-oriented PoC in
> places and must not be used to reinterpret these requirements.

## 1. Product boundary

Boomerang is a web-first returns workspace with a Chrome extension that operates inside the
user's existing retailer session.

- The **dashboard** is the product home. It presents normalized orders, deadlines, preferences,
  recommendations, and current return summaries stored for the user's account.
- The **extension** is the browser-execution surface. It reads live retailer pages, performs
  supervised reversible actions, and keeps detailed workflow/session state locally.
- The **API** authenticates the user, normalizes extension-supplied page data, persists account
  records, and serves the dashboard. It has no independent access to retailer accounts.
- The **parsing pipeline** processes bounded page content transiently. It does not become a durable
  store for retailer pages.

The central constraint is that the server learns about a retailer order only when the extension
sends information from a page the user can access. Google sign-in does not change that boundary.

## 2. Scope and priorities

### 2.1 Core v1

- Sign in with Google.
- A database-backed web dashboard.
- A visible extension connection state.
- Retailer order-page scanning using Manifest V3 APIs.
- Normalization of items, prices, dates, return policies, deadlines, and fees when available.
- Preference-based ranking and recommendations.
- Visible, supervised autofill for one uninterrupted return run.
- User review and confirmation before final submission.
- Recording printable-label and other manual-handoff outcomes.

### 2.2 Priority 1

- Record `qr_ready` when a retailer produces a QR-code return outcome.
- V1 stores the status only. Storage of a QR image, token, URL, or other representation is not
  authorized by this specification.

### 2.3 Priority 2

- Create a Google Calendar event after the user separately authorizes Calendar access and chooses
  **Add to calendar**.

### 2.4 Deferred

- Gmail API access and Gmail scraping.
- USPS, UPS, FedEx, paid pickup, pickup cancellation, and carrier tracking.
- Unattended retailer-account access.
- User-controlled Stop/Continue, interrupted-run reconciliation, and resumable automation.
- Asynchronous parsing unless measurement shows the synchronous contract is not viable.
- Browsers other than Chrome.

## 3. Architecture blocker register

The identifiers below give stable references to the ordered blockers in
[`ARCHITECTURE.md`](../docs/ARCHITECTURE.md#open-blockers). A requirement marked with one of these
identifiers is intentionally incomplete at that boundary.

| ID | Architecture blocker | What it prevents from being finalized |
|---|---|---|
| `ARCH-B1` | Interruption policy | The exact v1 behavior after a user, tab, page, or worker interrupts an automated run |
| `ARCH-B2` | AI runtime and contracts | Final normalization and per-step agent request shapes, timeouts, retries, payload limits, and hosting fit |
| `ARCH-B3` | Dashboard status evidence | The authoritative source for `handed_to_carrier` |
| `ARCH-B4` | Retention details | Record lifetimes, single-order deletion, checkpoint cleanup, backups, and recovery periods |
| `ARCH-B5` | Calendar design | Priority-2 component ownership, wire contracts, scope, token custody, refresh, revocation, and event-update behavior |
| `ARCH-B6` | Dashboard-to-extension bridge | How an authenticated dashboard addresses the correct extension workflow safely |
| `ARCH-B7` | Retailer target | Retailer-specific selectors, fixtures, policy assumptions, and acceptance tests |
| `ARCH-B8` | Complete-state semantics | The meaning, evidence, and legal transitions for `complete` |

## 4. Terminology

| Term | Meaning |
|---|---|
| **Normalized order** | Validated account data derived from a retailer page, not a stored page snapshot |
| **Policy fact** | A return rule, deadline, or fee extracted from the retailer page with available provenance or confidence |
| **Return summary** | The minimal durable state the dashboard needs for one item |
| **Workflow/session state** | Detailed browser-execution state for the current extension run |
| **Safe checkpoint** | A locally stored record of the last validated browser position and actions already performed |
| **Return method** | A retailer-presented way to complete a return, including its visible price and handoff form |
| **Retailer outcome** | The QR code, printable label, or manual-completion state produced by the retailer |

## 5. Functional requirements

### 5.1 Identity and account

**AUTH-01 — Google identity.** Boomerang SHALL support Sign in with Google and SHALL key the user
record by Google's stable OpenID Connect `sub` claim rather than by email address.

**AUTH-02 — Identity scopes.** Initial sign-in SHALL request only the identity information needed
to establish the account. It SHALL NOT request Gmail or Calendar access as a side effect of
sign-in.

**AUTH-03 — Independent retailer identity.** A Google identity SHALL NOT be treated as a retailer
credential or as authorization to access a retailer page.

**AUTH-04 — Authenticated account access.** Dashboard reads and mutations SHALL be scoped to the
authenticated Boomerang account.

### 5.2 Extension connection

**CONN-01 — Visible state.** The dashboard SHALL show whether a compatible extension is connected.

**CONN-02 — Account binding.** An extension connection SHALL be bound to the intended authenticated
Boomerang account and browser context.

**CONN-03 — Narrow command surface.** The dashboard-to-extension bridge SHALL expose only the
operations required by the return workflow. It SHALL NOT expose arbitrary script execution,
arbitrary tab access, or a general-purpose read of extension storage.

**CONN-04 — Final protocol blocked.** The transport, credentials, addressing, revocation, and
reconnection behavior for this bridge are blocked by `ARCH-B6`.

### 5.3 Extension permissions and page access

**EXT-01 — Minimal install permissions.** The extension manifest SHALL initially declare
`activeTab`, `scripting`, and `storage`, and no broad standing host access.

**EXT-02 — First scan gesture.** On first use, page access SHALL follow an explicit user gesture,
such as **Scan this page**, because `activeTab` does not authorize automatic injection on load.

**EXT-03 — Contextual host permission.** A standing retailer host permission MAY be requested only
after a successful user-initiated scan and in the context of that retailer.

**EXT-04 — Decline behavior.** Declining a standing host permission SHALL leave the explicit
scan-on-click path available.

**EXT-05 — Retailer-specific behavior blocked.** Concrete URL patterns, DOM signatures,
selectors, and fixture coverage are blocked by `ARCH-B7`.

### 5.4 Order ingestion and normalization

**INGEST-01 — Live-page source.** Order ingestion SHALL begin with a retailer page available in the
user's existing browser session. The backend SHALL NOT fetch or poll that page independently.

**INGEST-02 — Bounded subtree.** The extension SHALL select a bounded, sanitized order subtree
rather than transmitting the complete document.

**INGEST-03 — Data minimization.** The transmitted representation SHALL contain only information
needed to normalize orders and policies. It SHALL exclude scripts, retailer cookies,
authorization headers, passwords, payment fields, file inputs, and unrelated page content.

**INGEST-04 — Transient source data.** Raw DOM and the bounded, sanitized transmitted
representation SHALL be processed only for the current request and SHALL be discarded after
success or failure.

**INGEST-05 — Normalized output.** When available, normalization SHALL produce:

- retailer and retailer order identity;
- order items and item descriptions;
- item prices;
- ordered and delivered dates;
- return-policy rules;
- return deadlines;
- return fees; and
- provenance or confidence needed to distinguish retailer facts from derived values.

**INGEST-06 — Output validation.** Model output SHALL be treated as untrusted input and validated
for shape, type, length, plausible values, and permitted markup before persistence or rendering.

**INGEST-07 — Persistence.** Only validated normalized records SHALL be written to the account
database.

**INGEST-08 — Failure honesty.** If the page cannot be recognized or normalized, the user SHALL be
told that it could not be read. No partial or fabricated order SHALL be stored as a successful
parse.

**INGEST-09 — Provisional synchronous behavior.** The first contract MAY be synchronous, but the
final request shape, payload ceiling, latency budget, timeout, retry policy, and possible job model
are blocked by `ARCH-B2`.

### 5.5 Account data and state ownership

**DATA-01 — Database ownership.** The database SHALL be authoritative for:

- the Google-linked user record;
- normalized orders and items;
- prices and dates;
- parsed policy facts, deadlines, and fees;
- user preferences; and
- the current return summary shown on the dashboard.

**DATA-02 — Extension ownership.** `chrome.storage.local` SHALL be authoritative for:

- the workflow/session identifier and related database order/item identifiers;
- the current workflow state and retailer step;
- tab ID and last validated URL;
- the latest safe checkpoint;
- fields Boomerang filled;
- suggested and user-confirmed reason;
- selected return method; and
- attempt counts and timestamps.

**DATA-03 — No competing detailed state.** The database SHALL NOT maintain a second authoritative
copy of detailed workflow/session state or the latest safe checkpoint.

**DATA-04 — Summary publication.** The extension MAY update the database return summary only after
validating the live retailer page or receiving an explicit user action. The backend SHALL NOT infer
browser progress from an old summary alone.

**DATA-05 — Return-summary vocabulary.** The database return summary SHALL use these product states:
`not_started`, `in_progress`, `qr_ready`, `label_ready`, `handed_to_carrier`, and `complete`.

**DATA-06 — Handoff evidence blocked.** A `handed_to_carrier` record SHALL identify its evidence as
user-confirmed or retailer-observed. Which sources v1 supports is blocked by `ARCH-B3`.

**DATA-07 — Complete semantics blocked.** The meaning, evidence source, and legal transitions for
`complete` are blocked by `ARCH-B8`. Resolving carrier-handoff evidence under `ARCH-B3` SHALL NOT be
treated as resolving the `complete` state.

### 5.6 Dashboard

**DASH-01 — Product home.** The dashboard SHALL be the primary account-level surface for returns.

**DASH-02 — Required information.** The dashboard SHALL present:

- returns, carrier handoffs, and privacy navigation;
- extension connection state;
- returns closing soon;
- remaining returnable value;
- returns in progress;
- sorting by closing soonest;
- item, retailer, delivered date, price, days remaining, and return status; and
- an explanation of urgency thresholds and the selected return's next action.

**DASH-03 — Database-backed view.** Dashboard order, policy, preference, and summary data SHALL come
from the authenticated account database rather than directly from extension local storage.

**DASH-04 — Carrier-neutral handoff view.** The Pickups/handoffs area SHALL be a filtered view of
returns that reached carrier handoff. It SHALL NOT expose USPS booking, address, confirmation,
scheduling, or cancellation controls.

**DASH-05 — Honest status language.** A carrier-handoff state SHALL name its evidence and SHALL NOT
imply that Boomerang scheduled or observed a carrier pickup.

**DASH-06 — Privacy accuracy.** The dashboard SHALL state that normalized account data is stored on
Boomerang's servers. It SHALL NOT claim that nothing is stored server-side.

### 5.7 Urgency and preferences

**PREF-01 — Preference vocabulary.** V1 SHALL support:

- `lowest_cost`;
- `fastest_refund_or_replacement`;
- `no_printer`; and
- `more_sustainable`.

**PREF-02 — Ranking only.** Preferences MAY rank and explain return methods. They SHALL NOT hide a
visible method, select a reason, select a return method, submit a form, or authorize a fee.

**PREF-03 — Complete choices.** Every visible return method SHALL remain available to the user with
its known price. An unreadable price SHALL be shown as unknown rather than treated as zero.

**PREF-04 — Missing facts.** When the page does not expose facts required to apply a preference,
Boomerang SHALL say so rather than invent a ranking.

**PREF-05 — Deadline honesty.** Derived or uncertain deadlines SHALL be distinguished from dates
stated by the retailer. Missing deadlines SHALL remain visible as unknown.

### 5.8 Supervised return execution

**RETURN-01 — Explicit start.** A return run SHALL begin only after an explicit user action naming
the item to return.

**RETURN-02 — Visible operation.** The extension SHALL open or focus a visible retailer tab and
operate while the user can observe the flow.

**RETURN-03 — Agent-first step planning.** For every return-flow step, the extension SHALL send the
agent a bounded, sanitized representation of the current live DOM and request a proposal before any
browser action is executed. Bundled selectors MAY assist page recognition, target resolution, and
validation, but SHALL NOT construct or execute an action or skip the agent request.

**RETURN-04 — Exactly one closed tool call.** The agent SHALL propose exactly one tool call per step,
limited to:

- `click`;
- `select_option`;
- `fill`;
- `pause_for_user`;
- `report_stuck`; and
- `report_outcome`.

In v1, `report_outcome` SHALL accept only `qr_ready` or `label_ready` and SHALL carry no QR or label
artifact. `handed_to_carrier` and `complete` SHALL remain invalid values until `ARCH-B3` and
`ARCH-B8`, respectively, are resolved.

**RETURN-05 — Live external validation.** Trusted extension code SHALL validate every agent
proposal against the current live DOM, allowed target types, and user-confirmation rules immediately
before executing a browser action or publishing an outcome. A stale, invalid, or unsupported
proposal SHALL execute and publish nothing and become a manual handoff rather than an expanded tool
call.

**RETURN-06 — Fill restrictions.** `fill` SHALL target only reversible, permitted fields and SHALL
never target password, payment, or file-upload inputs.

**RETURN-07 — Suggested reason.** A suggested return reason SHALL be presented as an editable
default for review, not as authority to submit it.

**RETURN-08 — Irreversible actions.** Final submission and any other irreversible action SHALL
require explicit user confirmation.

**RETURN-09 — Method choice.** The user SHALL choose the return method. Boomerang SHALL NOT silently
select a method or escalate to a paid option.

**RETURN-10 — Unknown or divergent state.** When the page cannot be recognized or the run loses a
known safe state, the extension SHALL leave the tab available and hand control to the user instead
of guessing.

**RETURN-11 — Uninterrupted v1 contract.** V1 SHALL NOT promise recovery or continuation after the
user takes over, a tab diverges, or execution is interrupted. The exact fallback acceptance
criteria are blocked by `ARCH-B1`.

**RETURN-12 — Checkpoint does not imply resume.** Persisting a safe checkpoint SHALL NOT be
presented as support for Stop/Continue or interrupted-run resumption.

### 5.9 Retailer outcomes

**OUTCOME-01 — Retailer authority.** QR codes and printable labels SHALL be produced by the retailer,
not manufactured by Boomerang.

**OUTCOME-02 — QR success.** A QR-code outcome SHALL be treated as a successful return outcome and
SHALL set the durable summary to `qr_ready`.

**OUTCOME-03 — QR storage limit.** V1 SHALL persist only `qr_ready`; the QR representation itself
SHALL NOT be persisted until a later decision authorizes its format, protection, retention, and
deletion.

**OUTCOME-04 — Printable label.** A printable-label outcome SHALL set the durable summary to
`label_ready` without implying carrier handoff.

**OUTCOME-05 — Manual completion.** An unknown or unsupported retailer outcome SHALL leave the tab
open for manual completion and update the dashboard only with facts the user or live page confirms.

### 5.10 Google Calendar, priority 2

This section preserves the priority-2 product boundary only. Calendar component ownership, OAuth
flow, credential custody, and wire contracts SHALL remain outside the current low-level
implementation design until priority 2 is taken up and `ARCH-B5` is resolved.

**CAL-01 — Incremental consent.** Calendar permission SHALL be requested separately when the user
chooses **Add to calendar**, not during initial sign-in.

**CAL-02 — Narrow purpose.** Calendar access SHALL be used to create a return-deadline or
user-selected follow-up event. It SHALL NOT read availability.

**CAL-03 — Core flow independence.** Calendar authorization or event creation failure SHALL NOT
invalidate a return or block the core return workflow.

**CAL-04 — Credential design blocked.** The final OAuth scope, client/server token custody,
refresh-token behavior, revocation path, and event-update behavior are blocked by `ARCH-B5`.

### 5.11 Privacy, retention, and deletion

**PRIV-01 — Never persisted.** Boomerang SHALL NOT durably store raw DOM, bounded sanitized DOM
representations, retailer cookies, authorization headers, passwords, payment fields, file inputs,
or raw label or QR artifacts.

**PRIV-02 — Terminal-page egress.** A bounded, sanitized terminal-page representation MAY reach the
agent. Before transmission, the extension SHALL remove raw label artifacts, QR contents, addresses,
barcodes, and protected URLs.

**PRIV-03 — Database disclosure.** The Privacy surface and extension disclosure SHALL explain
database storage, Google identity, model processing, extension-local workflow state, and Calendar
authorization accurately.

**PRIV-04 — Account deletion baseline.** Account deletion SHALL remove the user's normalized
orders, items, policies, preferences, and return summaries from the database.

**PRIV-05 — Local clearing semantics.** Clearing extension data SHALL remove local workflow/session
state and checkpoints but SHALL NOT silently delete the user's web account or database records.

**PRIV-06 — Calendar disconnect.** Disconnecting Calendar SHALL revoke access and remove any stored
Calendar credential if the final design stores one.

**PRIV-07 — Detailed lifecycle blocked.** Completed-order retention, expired-order retention,
single-order deletion, checkpoint cleanup, backup expiry, recovery periods, and token lifetimes are
blocked by `ARCH-B4`.

## 6. Non-functional requirements

### 6.1 Security

**SEC-01.** Retailer page content and model output SHALL be treated as untrusted input.

**SEC-02.** Page-derived text SHALL be rendered as text, not executable markup.

**SEC-03.** Retailer cookies and credentials SHALL remain in the browser.

**SEC-04.** The extension SHALL hold no server, model-provider, Calendar-client, or retailer secret.

**SEC-05.** Authorization checks SHALL be enforced by trusted application code, not by retailer DOM
or model output.

**SEC-06.** Logs and telemetry SHALL exclude raw DOM, credentials, sensitive form fields, and
Calendar tokens.

### 6.2 Reliability and user control

**REL-01.** A failure to parse, rank, connect, or automate SHALL preserve a manual route through the
visible retailer page.

**REL-02.** A retailer-specific failure SHALL not make unrelated retailer data unavailable.

**REL-03.** Database summaries and extension-local execution state SHALL never be silently treated
as interchangeable.

**REL-04.** Retrying a request SHALL not duplicate an irreversible retailer action.

### 6.3 Performance

**PERF-01.** Dashboard and extension surfaces SHALL show a clear pending state while normalization
is running.

**PERF-02.** Browser actions SHALL not wait indefinitely on agent inference; on timeout the flow
SHALL hand control to the user. It SHALL NOT take a selector-only action as a fallback.

**PERF-03.** Concrete normalization and per-step agent latency, timeout, retry, payload, and
hosting-runtime requirements remain blocked by `ARCH-B2`.

### 6.4 Compliance and transparency

**COMP-01.** Chrome Web Store disclosures and product Privacy copy SHALL describe the same data
collection, transmission, and persistence behavior.

**COMP-02.** The product SHALL distinguish Google identity consent from Calendar authorization.

**COMP-03.** The product SHALL never imply Gmail access, carrier scheduling, or carrier observation
that does not exist.

## 7. Acceptance boundary

The design is ready to drive a new implementation plan when:

- every unblocked requirement maps to a component and verification approach in the high- and
  low-level designs;
- every incomplete contract names one or more `ARCH-B*` blockers;
- no active requirement depends on USPS pickup or the previous local-only architecture;
- the first retailer is chosen or retailer-specific work remains explicitly blocked by `ARCH-B7`;
- the normalization and per-step agent contracts are measured or remain explicitly blocked by
  `ARCH-B2`; and
- the task decomposition under `plan/tasks/` and workspace guidance are reconciled in separate
  follow-up changes.
