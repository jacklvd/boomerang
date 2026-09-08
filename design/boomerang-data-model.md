# Boomerang Data Model

## Status

This document defines the shared logical data model for the dashboard, extension UI, and server.
It is an implementation contract for parallel frontend and backend work, not a physical database
schema.

The product and architecture documents under [`../docs/`](../docs/) remain the source of truth.
If this document conflicts with them, update this document rather than treating the conflict as a
new product decision.

## 1. Scope

This contract covers:

- the account, order, item, policy, preference, and return-summary records already required by the
  product;
- read models needed by the dashboard and extension UI;
- the minimum extension-local workflow record needed to render an active run; and
- validation rules that must be shared across implementations.

This contract intentionally does not define:

- raw or sanitized DOM representations;
- model prompts, responses, tool calls, or the agent execution pipeline;
- raw labels, QR contents, addresses, barcodes, or protected artifact URLs;
- Calendar models or synchronization state;
- a dashboard-to-extension bridge transport;
- carrier pickup records;
- the physical database product, indexes, migrations, or backup policy.

The following decisions remain blocked:

- `ARCH-B3`: which component may publish `handed_to_carrier`;
- `ARCH-B6`: how the dashboard connects to and launches the extension;
- `ARCH-B8`: the meaning and allowed transitions of `complete`.

## 2. Model layers

Boomerang uses three related model layers. Keeping them distinct prevents UI convenience fields from
becoming accidental database authority.

| Layer | Owner | Purpose |
|---|---|---|
| Persistence model | Server | Durable source of truth for account and return-candidate data |
| API read model | Server API | UI-ready projection with derived urgency, metrics, and next actions |
| Workflow model | Extension local storage | Current browser-run state and safe checkpoints |

The database does not store raw or sanitized DOM. The extension does not become authoritative for
orders, policies, preferences, or dashboard summaries merely because it caches an API response.

## 3. Shared conventions

### 3.1 Identifiers

- Every identifier is an opaque, case-sensitive string on the wire.
- Clients must not infer entity type, creation time, or relationships from an identifier.
- Example values use readable prefixes only to make fixtures easier to understand.

### 3.2 Dates and time

- A calendar date is an ISO 8601 full date: `YYYY-MM-DD`.
- A timestamp is an RFC 3339 UTC instant, for example `2026-09-05T18:22:41Z`.
- `days_remaining` is derived at response time from `return_by` and the server's date. It is never
  an authoritative stored fact.

### 3.3 Money

Money is represented in integer minor units. Floating-point amounts are prohibited.

```json
{
  "amount_minor": 8999,
  "currency": "USD"
}
```

`currency` is an uppercase ISO 4217 currency code. Amounts with different currencies must never be
summed into one value.

### 3.4 Null and missing facts

- `null` means the fact is currently unknown or unavailable.
- An omitted field means the field is not part of that representation.
- The server and extension must not invent dates, prices, fees, or policy facts to replace `null`.

### 3.5 Versioning

- `ReturnPolicy.version` is internal metadata for reconciling normalization updates. It is not part
  of the dashboard wire projection.
- `PreferenceSet` and `ReturnSummary` do not expose record versions in v1.
- `schema_version` versions an extension-local record shape.

## 4. Closed vocabularies

These values are closed for API version `v1`. An unknown value must fail validation rather than be
silently mapped to a familiar value.

### 4.1 Return state

```text
not_started
in_progress
qr_ready
label_ready
handed_to_carrier
complete
```

`handed_to_carrier` and `complete` are reserved values in the shared vocabulary, but writes to those
states are blocked until `ARCH-B3` and `ARCH-B8` are resolved respectively.

### 4.2 Preference

```text
lowest_cost
fastest_refund_or_replacement
no_printer
more_sustainable
```

A user may choose zero or more values. The collection is a set; array order has no meaning.

### 4.3 Policy eligibility

```text
eligible
ineligible
unknown
```

### 4.4 Fact origin

```text
retailer_stated
derived
user_confirmed
```

### 4.5 Return-summary update source

```text
system_initialization
extension_live_page
user_confirmed
```

`system_initialization` is valid only for the server-created `not_started` summary.

### 4.6 Carrier handoff evidence

```text
user_confirmed
retailer_observed
```

This vocabulary is defined now so the UI and models do not invent alternatives. Which component may
submit either value remains `ARCH-B3`.

### 4.7 Urgency level

```text
expired
critical
soon
later
unknown
```

Thresholds are server configuration returned with the dashboard response. Frontends must not
hardcode day ranges.

## 5. Reusable value objects

### 5.1 `Money`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `amount_minor` | integer | yes | May be zero; negative values are invalid |
| `currency` | string | yes | Three uppercase ISO 4217 characters |

### 5.2 `SourcedDate`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `value` | date | yes | ISO full date |
| `origin` | `FactOrigin` | yes | Provenance of this fact |
| `confidence` | number or `null` | yes | `0.0` through `1.0`; normally `null` for an explicit retailer statement |

### 5.3 `SourcedMoney`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `value` | `Money` | yes | — |
| `origin` | `FactOrigin` | yes | Provenance of this fact |
| `confidence` | number or `null` | yes | `0.0` through `1.0` |

Source metadata must describe provenance without retaining raw DOM, selectors, screenshots, or page
text.

## 6. Server persistence models

The tables below define logical records and constraints. They do not prescribe table names or an
ORM.

### 6.1 `Account`

| Field | Type | Required | Visibility and rule |
|---|---|---:|---|
| `id` | opaque ID | yes | Public account identifier |
| `google_subject` | string | yes | Server-only; unique; the stable identity key |
| `email` | string or `null` | yes | Profile display/sign-in context only; never the identity key |
| `display_name` | string or `null` | yes | Basic profile field |
| `avatar_url` | string or `null` | yes | Basic profile field; must be HTTPS when present |
| `created_at` | timestamp | yes | Immutable |
| `updated_at` | timestamp | yes | — |

The Google `sub` claim is authoritative for identity. Email changes must not create, merge, or select
an account.

### 6.2 `Order`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `id` | opaque ID | yes | — |
| `account_id` | opaque ID | yes | Owning account |
| `retailer_key` | string | yes | Stable internal retailer identifier |
| `retailer_name` | string | yes | Display label captured for this order |
| `retailer_order_reference` | string or `null` | yes | Unique within the account and retailer when available |
| `ordered_on` | date or `null` | yes | Do not derive when absent |
| `created_at` | timestamp | yes | — |
| `updated_at` | timestamp | yes | — |

### 6.3 `OrderItem`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `id` | opaque ID | yes | Dashboard and return workflow unit of identity |
| `order_id` | opaque ID | yes | Parent order |
| `description` | string | yes | Human-readable product name |
| `variant` | string or `null` | yes | Size, color, or other concise variant text |
| `quantity` | positive integer | yes | At least `1` |
| `price` | `Money` or `null` | yes | Total known paid value represented by this item row, after item-level discounts |
| `delivered_on` | date or `null` | yes | Item-level to support split shipments |
| `created_at` | timestamp | yes | — |
| `updated_at` | timestamp | yes | — |

Each return candidate is an `OrderItem`. The item identifier, not the order identifier, is used for
policy and return-summary endpoints. `price` already covers the row's `quantity`; metric code must
not multiply it by `quantity` again.

### 6.4 `ReturnPolicy`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `item_id` | opaque ID | yes | One current policy record per item |
| `eligibility` | `PolicyEligibility` | yes | — |
| `return_by` | `SourcedDate` or `null` | yes | Authoritative deadline fact when known |
| `fee` | `SourcedMoney` or `null` | yes | Known return fee; `null` does not mean free |
| `rules` | array of `PolicyRule` | yes | May be empty |
| `version` | positive integer | yes | Concurrency version |
| `updated_at` | timestamp | yes | — |

`PolicyRule` has the following shape:

| Field | Type | Required | Rule |
|---|---|---:|---|
| `id` | opaque ID | yes | Stable within the policy version |
| `text` | string | yes | Concise normalized fact, not a page-text excerpt |
| `origin` | `FactOrigin` | yes | — |
| `confidence` | number or `null` | yes | `0.0` through `1.0` |

### 6.5 `PreferenceSet`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `account_id` | opaque ID | yes | Exactly one set per account |
| `values` | array of `Preference` | yes | Unique values; may be empty; order has no meaning |
| `updated_at` | timestamp | yes | — |

### 6.6 `ReturnSummary`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `item_id` | opaque ID | yes | Exactly one current summary per item |
| `state` | `ReturnState` | yes | Closed vocabulary |
| `update_source` | `ReturnSummaryUpdateSource` | yes | Must satisfy the invariants below |
| `handoff_evidence` | `HandoffEvidence` or `null` | yes | Non-null only for `handed_to_carrier` |
| `observed_at` | timestamp | yes | When the source observed or confirmed the state |
| `updated_at` | timestamp | yes | Server write time |

A newly created item receives a server-created summary with:

```json
{
  "item_id": "item_01",
  "state": "not_started",
  "update_source": "system_initialization",
  "handoff_evidence": null,
  "observed_at": "2026-09-01T20:03:00Z",
  "updated_at": "2026-09-01T20:03:00Z"
}
```

For `system_initialization`, `observed_at` and `updated_at` are both the server timestamp at which
the initial summary is created.

The summary stores only the normalized outcome. It must never contain a raw label, QR contents,
address, barcode, or protected URL.

## 7. API read models

### 7.1 `AccountView`

`AccountView` contains `id`, `email`, `display_name`, and `avatar_url`. It never exposes
`google_subject`.

### 7.2 `Urgency`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `level` | `UrgencyLevel` | yes | — |
| `days_remaining` | integer or `null` | yes | Derived as of the enclosing response timestamp |

When `return_by` is unknown, urgency is `unknown` and `days_remaining` is `null`. A negative number
means the deadline has passed.

### 7.3 `NextAction`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `code` | string enum | yes | One of the values below |
| `label` | string | yes | UI-ready display label |

`code` is one of:

```text
start_return
focus_active_return
open_retailer_result
manual_required
none
```

`NextAction` is advisory business state. It does not authorize a state transition and it does not
define the `ARCH-B6` launch transport. The frontend determines whether the action can currently be
invoked by composing this value with extension state obtained outside the server API.

The server derives `NextAction` using the first matching row below. Workflow progress takes
precedence over later policy or deadline projections because it records a validated return
milestone.

| Precedence | Return state | Additional condition | Action code | Canonical label |
|---:|---|---|---|---|
| 1 | `qr_ready` | Any eligibility or urgency | `open_retailer_result` | `Open return result` |
| 2 | `label_ready` | Any eligibility or urgency | `open_retailer_result` | `Open return result` |
| 3 | `in_progress` | Any eligibility or urgency | `focus_active_return` | `Continue return` |
| 4 | `not_started` | `eligibility = ineligible` | `manual_required` | `Continue manually` |
| 5 | `not_started` | `urgency = expired` | `manual_required` | `Continue manually` |
| 6 | `not_started` | Eligibility is `eligible` or `unknown`, and urgency is `critical`, `soon`, `later`, or `unknown` | `start_return` | `Start return` |
| 7 | `handed_to_carrier` | Any eligibility or urgency | `none` | `No action` |
| 8 | `complete` | Any eligibility or urgency | `none` | `No action` |

The labels in this table are part of the v1 wire contract. Deriving `none` for
`handed_to_carrier` and `complete` is defensive read behavior only; it does not resolve `ARCH-B3`
or `ARCH-B8`, authorize either write, or define the meaning of `complete`.

### 7.4 `ReturnCandidate`

The dashboard row and the nested `candidate` in the item-detail view share this shape:

```json
{
  "item_id": "item_01",
  "order_id": "order_01",
  "retailer": {
    "key": "retailer_a",
    "name": "Example Retailer"
  },
  "order_reference": "ORDER-1001",
  "item": {
    "description": "Trail running shoes",
    "variant": "Blue / 10",
    "quantity": 1,
    "price": {
      "amount_minor": 8999,
      "currency": "USD"
    }
  },
  "dates": {
    "ordered_on": "2026-08-24",
    "delivered_on": "2026-08-29",
    "return_by": {
      "value": "2026-09-12",
      "origin": "retailer_stated",
      "confidence": null
    }
  },
  "policy": {
    "eligibility": "eligible",
    "fee": null,
    "rules": []
  },
  "urgency": {
    "level": "soon",
    "days_remaining": 7
  },
  "return_summary": {
    "state": "not_started",
    "update_source": "system_initialization",
    "handoff_evidence": null,
    "observed_at": "2026-09-01T20:03:00Z",
    "updated_at": "2026-09-01T20:03:00Z"
  },
  "next_action": {
    "code": "start_return",
    "label": "Start return"
  }
}
```

In this projection, `order_reference`, `item.variant`, `item.price`, `dates.ordered_on`,
`dates.delivered_on`, `dates.return_by`, and `policy.fee` may be `null` when the corresponding fact
is unknown. The UI rules in the API contract define how those cases are presented.

No label or QR artifact is present in this model. `open_retailer_result` means the user can be sent
back to the retailer-owned result page; it does not mean Boomerang stores that result.

### 7.5 `ReturnCandidateDetail`

The item-detail endpoint wraps a `ReturnCandidate` with the timestamp used for its temporal
projections:

| Field | Type | Required | Rule |
|---|---|---:|---|
| `generated_at` | timestamp | yes | Snapshot time used to derive `candidate.urgency` |
| `candidate` | `ReturnCandidate` | yes | Exact candidate shape defined above |

For dashboard candidates, `days_remaining` and urgency are derived as of `metrics.as_of`. For an
item-detail response, they are derived as of `generated_at`.

### 7.6 `DashboardMetrics`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `as_of` | timestamp | yes | Calculation instant |
| `closing_soon_max_days` | non-negative integer | yes | Current server threshold used for `closing_soon_count` |
| `closing_soon_count` | non-negative integer | yes | Candidates satisfying the exact predicate below |
| `in_progress_count` | non-negative integer | yes | Candidates in `in_progress` |
| `carrier_handoff_count` | non-negative integer | yes | Candidates in `handed_to_carrier` |
| `returnable_value_by_currency` | array of `Money` | yes | Remaining known value, separated by currency |

A candidate contributes to `closing_soon_count` if and only if all of these conditions are true:

- `days_remaining` is not `null`;
- `0 <= days_remaining <= closing_soon_max_days`;
- policy eligibility is `eligible` or `unknown`; and
- return state is neither `handed_to_carrier` nor `complete`.

Consequently, expired candidates, known-ineligible candidates, and candidates with unknown
deadlines do not count. Candidates in `qr_ready` or `label_ready` do count because carrier handoff
may still be required. Unknown eligibility remains included so uncertain policy data does not hide
a known approaching deadline. Price has no effect on this count, and dashboard list filters do not
change this account-wide metric.

For the v1 dashboard, “remaining returnable value” includes candidates that:

- are not `handed_to_carrier` or `complete`;
- are not known to be ineligible;
- are not past a known deadline; and
- have a known price.

It excludes unknown prices instead of treating them as zero.
It uses item value before any return fee; fees are shown separately and are not silently deducted
from the headline value.

### 7.7 `UrgencyLegendEntry`

| Field | Type | Required | Rule |
|---|---|---:|---|
| `level` | `UrgencyLevel` | yes | Excludes `unknown` only if the UI supplies its own unknown label |
| `label` | string | yes | Display label |
| `min_days` | integer or `null` | yes | Inclusive lower bound |
| `max_days` | integer or `null` | yes | Inclusive upper bound |

The dashboard response supplies the legend so the UI renders the same thresholds used by the
server.

## 8. Extension-local workflow model

`WorkflowSession` lives in extension local storage. It is not posted to the server as a whole.

| Field | Type | Required | Rule |
|---|---|---:|---|
| `schema_version` | positive integer | yes | Starts at `1` |
| `id` | opaque ID | yes | Workflow-session identifier |
| `account_id` | opaque ID | yes | Owning signed-in account |
| `order_id` | opaque ID | yes | — |
| `item_id` | opaque ID | yes | — |
| `run_status` | enum | yes | `active`, `awaiting_user`, `manual_handoff`, or `terminal` |
| `retailer_step` | string | yes | Adapter-defined, non-sensitive step name |
| `tab_id` | integer | yes | Browser-local tab identifier |
| `last_validated_url` | string | yes | Retailer page URL; never synced to the server |
| `safe_checkpoint` | `SafeCheckpoint` or `null` | yes | Most recent validated checkpoint |
| `fields_filled` | array of `FilledField` | yes | Field names only; never submitted values |
| `suggested_reason` | string or `null` | yes | Local suggestion |
| `user_confirmed_reason` | string or `null` | yes | Local user-confirmed choice |
| `selected_return_method` | `SelectedReturnMethod` or `null` | yes | Local user-confirmed method |
| `attempt_count` | non-negative integer | yes | Number of action attempts in this run |
| `started_at` | timestamp | yes | — |
| `updated_at` | timestamp | yes | — |

`SafeCheckpoint` contains:

| Field | Type | Required | Rule |
|---|---|---:|---|
| `observation_id` | opaque ID | yes | References an in-memory observation for the active run only |
| `retailer_step` | string | yes | Step validated at this checkpoint |
| `url` | string | yes | Extension-local only |
| `completed_action_count` | non-negative integer | yes | — |
| `recorded_at` | timestamp | yes | — |

`FilledField` contains `semantic_name` and `filled_at`. It never contains the value entered.

`SelectedReturnMethod` contains:

| Field | Type | Required | Rule |
|---|---|---:|---|
| `method_id` | string | yes | Retailer-session-local identifier |
| `label` | string | yes | User-visible method label |
| `price` | `Money` or `null` | yes | `null` means unknown, not free |
| `selected_at` | timestamp | yes | Must follow explicit user choice |

`awaiting_user` describes the current supervised run. It does not promise pause/resume across tab
closure, browser restart, or URL drift.

## 9. Relationships and ownership

```text
Account 1 ── * Order 1 ── * OrderItem
                              │
                              ├── 1 ReturnPolicy
                              └── 1 ReturnSummary

Account 1 ── 1 PreferenceSet

OrderItem 1 ── 0..1 active extension-local WorkflowSession
```

All server reads and writes are scoped through the authenticated account. Looking up another
account's identifier must behave as not found; it must not reveal that the entity exists.

## 10. Cross-model invariants

1. Every `OrderItem` belongs to the same account as its parent `Order`.
2. A `ReturnPolicy` and `ReturnSummary` may exist only for an existing item.
3. `system_initialization` may write only `not_started`.
4. `handoff_evidence` must be `null` unless the state is `handed_to_carrier`.
5. A `handed_to_carrier` write is rejected until `ARCH-B3` is resolved.
6. A `complete` write is rejected until `ARCH-B8` is resolved.
7. Preference values are unique and drawn only from the closed vocabulary.
8. `days_remaining`, urgency, metrics, and next actions are projections, not durable authority.
9. Neither server models nor API read models contain raw DOM or sensitive label artifacts.
10. `NextAction` follows the precedence table in section 7.3 and does not encode client invocation
    availability.
11. `closing_soon_count` follows the exact predicate in section 7.6 and is independent of list
    filters and price.

## 11. Parallel implementation boundary

The frontend may build against `AccountView`, `ReturnCandidate`, `ReturnCandidateDetail`,
`DashboardMetrics`, `UrgencyLegendEntry`, and `PreferenceSet` immediately using fixtures.

The backend/model implementation may independently create persistence entities and projection
mappers as long as it preserves the wire field names and invariants above. ORM names, table layout,
and internal identifiers do not need to match this document.

The HTTP routes and complete request/response examples are defined in
[`boomerang-api-contract.md`](boomerang-api-contract.md).
