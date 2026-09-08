# Boomerang Dashboard and Extension API Contract

## Status

This document defines the version `v1` HTTP contract needed for the dashboard and extension UI to
work in parallel with the server model implementation.

The shared types and persistence invariants are defined in
[`boomerang-data-model.md`](boomerang-data-model.md). The product and architecture documents under
[`../docs/`](../docs/) remain the source of truth.

This is a contract-first design. The routes do not need to exist before frontend work starts;
frontend fixtures and server contract tests should use the exact shapes below.

## 1. Scope

The v1 UI contract provides:

- the signed-in account profile;
- a dashboard aggregate with metrics, urgency legend, return candidates, and pagination;
- one return-candidate detail view;
- preference reads and writes;
- extension publication of supported return-summary states; and
- account deletion.

It does not provide:

- order-page ingestion or parsing;
- model or agent execution endpoints;
- DOM upload endpoints;
- label, QR, barcode, address, or protected-URL storage;
- Calendar endpoints;
- carrier pickup endpoints;
- an endpoint that starts or controls a retailer workflow; or
- a dashboard-to-extension messaging transport.

Those exclusions keep the current contract usable without prematurely resolving the AI pipeline,
Calendar priority, or `ARCH-B6`.

## 2. Stability boundary

The following are stable for parallel v1 implementation:

- route paths and HTTP methods in section 5;
- request and response field names;
- date, timestamp, money, identifier, and null conventions;
- the current closed enum values;
- error response shape; and
- ownership and return-state validation rules.

The following are intentionally not frozen:

- whether the application session is carried by a secure cookie or bearer token;
- the Google credential-exchange/login endpoint;
- how a dashboard action reaches the extension;
- writes to `handed_to_carrier` or `complete`; and
- database and ORM structure.

Changing an unfrozen implementation detail must not change the stable response bodies in this
document.

## 3. HTTP conventions

### 3.1 Base path and content type

- API base path: `/v1`
- Request and response media type: `application/json`
- Existing service health checks remain outside this contract at `/health`.

Request objects reject unknown fields with `422 validation_failed`. This catches contract drift
early. Response objects may gain optional fields within v1; clients must ignore response fields they
do not understand.

Adding a new value to a closed v1 enum is a breaking change and requires coordination.

### 3.2 Authentication and account scope

Every `/v1` route in this document requires an authenticated application principal. The server maps
that principal to an account using the Google `sub` identity claim. Clients never submit an
`account_id` to choose the account being accessed.

The session transport is deliberately unresolved. Frontend code should put authentication behind a
single client adapter so a cookie/token decision does not affect feature components.

An item identifier belonging to another account returns `404 not_found`, not `403`, so the API does
not reveal cross-account existence.

### 3.3 Request correlation

The server returns an opaque `X-Request-ID` response header. Error bodies repeat it in `request_id`
so the UI can show a support reference without exposing an exception or sensitive payload.

### 3.4 Caching

Authenticated order and return responses use:

```http
Cache-Control: private, no-store
```

The browser may hold the current response in application memory, but shared HTTP caches must not
store it.

## 4. Error contract

Every non-success response uses this body:

```json
{
  "reason": "validation_failed",
  "message": "One or more fields are invalid.",
  "request_id": "req_01K4A6W0K45P8N9FQF5A7B3C2D",
  "details": {
    "fields": [
      {
        "path": "values[0]",
        "message": "Unknown preference value."
      }
    ]
  }
}
```

`message` is safe to display. `details` is an object or `null` and must not contain raw upstream
responses, stack traces, DOM, tokens, artifact contents, addresses, or protected URLs.

| Status | `reason` | When used |
|---:|---|---|
| 400 | `invalid_request` | Malformed JSON or request syntax |
| 401 | `unauthenticated` | No valid application principal |
| 404 | `not_found` | Resource absent or outside the account scope |
| 409 | `state_transition_not_allowed` | Transition is invalid from the current state |
| 409 | `state_blocked` | State exists in the vocabulary but its decision blocker is unresolved |
| 422 | `validation_failed` | A typed field or invariant is invalid |
| 429 | `rate_limited` | Caller exceeded an enforced limit |
| 500 | `internal_error` | Unexpected server failure |
| 503 | `temporarily_unavailable` | A required service is temporarily unavailable |

## 5. Endpoint summary

| Method | Path | Caller | Purpose |
|---|---|---|---|
| `GET` | `/v1/me` | Dashboard or extension | Current account profile |
| `GET` | `/v1/dashboard` | Dashboard or extension | Metrics, urgency legend, candidates, and pagination |
| `GET` | `/v1/items/{item_id}` | Dashboard or extension | One return-candidate detail |
| `GET` | `/v1/preferences` | Dashboard or extension | Current preference set |
| `PUT` | `/v1/preferences` | Dashboard or extension | Replace preference set |
| `PUT` | `/v1/items/{item_id}/return-summary` | Extension | Publish a supported normalized state |
| `DELETE` | `/v1/account` | Dashboard | Delete the active account and primary records |

There is deliberately no `/start-return` route. Starting or focusing a retailer workflow is a local
dashboard-to-extension action whose transport remains `ARCH-B6`; the backend must not attempt to
drive the retailer page.

## 6. `GET /v1/me`

Returns the current `AccountView`.

### Response: `200 OK`

```json
{
  "id": "acct_01K4A4ZMVN08VK0Y6FMV7D0SXC",
  "email": "sam@example.com",
  "display_name": "Sam",
  "avatar_url": "https://example.com/avatar.png"
}
```

`email`, `display_name`, and `avatar_url` may each be `null`. The Google subject is never exposed.

## 7. `GET /v1/dashboard`

Returns one UI-ready dashboard snapshot. It contains exactly four top-level concerns: `metrics`,
`urgency_legend`, `candidates`, and `page`. Account data comes from `GET /v1/me`. Extension
connection state is determined and composed by the frontend, not by the server.

### Query parameters

| Parameter | Type | Default | Rule |
|---|---|---|---|
| `sort` | string | `closing_soonest` | Only `closing_soonest` is defined in v1 |
| `state` | repeated `ReturnState` | all | Example: `?state=not_started&state=in_progress` |
| `urgency` | repeated `UrgencyLevel` | all | Example: `?urgency=critical&urgency=soon` |
| `limit` | integer | `50` | `1` through `100` |
| `cursor` | string | absent | Opaque cursor returned by the prior page |

With `closing_soonest`, known deadlines sort by date ascending, including already expired dates;
unknown deadlines sort last. Stable ties use retailer name and then item ID. Clients must not
re-sort by locally calculated day counts.

Filters affect `candidates` and pagination only. `metrics` remains account-wide so headline cards do
not change when the list is filtered.

`closing_soon_count` uses the exact predicate defined by the data model. A candidate counts only
when `days_remaining` is not `null`, the value is between `0` and
`closing_soon_max_days` inclusive, policy eligibility is `eligible` or `unknown`, and return state
is neither `handed_to_carrier` nor `complete`. Price does not affect the count. Thus expired,
known-ineligible, and unknown-deadline candidates do not count, while `qr_ready` and `label_ready`
candidates within the day boundary do count.

Every candidate's `next_action` follows the normative precedence and canonical labels in the data
model. The server derives advisory business state only; each frontend separately composes action
availability from extension connectivity and local capabilities.

### Response: `200 OK`

```json
{
  "metrics": {
    "as_of": "2026-09-05T18:22:41Z",
    "closing_soon_max_days": 7,
    "closing_soon_count": 1,
    "in_progress_count": 0,
    "carrier_handoff_count": 0,
    "returnable_value_by_currency": [
      {
        "amount_minor": 8999,
        "currency": "USD"
      }
    ]
  },
  "urgency_legend": [
    {
      "level": "expired",
      "label": "Deadline passed",
      "min_days": null,
      "max_days": -1
    },
    {
      "level": "critical",
      "label": "Act now",
      "min_days": 0,
      "max_days": 2
    },
    {
      "level": "soon",
      "label": "Closing soon",
      "min_days": 3,
      "max_days": 7
    },
    {
      "level": "later",
      "label": "More time",
      "min_days": 8,
      "max_days": null
    },
    {
      "level": "unknown",
      "label": "Deadline unknown",
      "min_days": null,
      "max_days": null
    }
  ],
  "candidates": [
    {
      "item_id": "item_01K4A58C80H75R0N9FK6E4K2AQ",
      "order_id": "order_01K4A55XPHQEE0JJ4MRCJBY0YR",
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
  ],
  "page": {
    "next_cursor": null
  }
}
```

### Empty dashboard

An account with no candidates returns empty `candidates` and value arrays, zero counts, and
`next_cursor: null`. It is a successful `200`, not `404`.

## 8. `GET /v1/items/{item_id}`

Returns one `ReturnCandidateDetail`. The nested `candidate` uses the exact candidate shape from the
dashboard response, and `generated_at` is the snapshot timestamp used to calculate its urgency.

### Response: `200 OK`

```json
{
  "generated_at": "2026-09-05T18:22:41Z",
  "candidate": {
    "item_id": "item_01K4A58C80H75R0N9FK6E4K2AQ",
    "order_id": "order_01K4A55XPHQEE0JJ4MRCJBY0YR",
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
}
```

The server recalculates urgency and next action as of `generated_at`. A client must not assume the
projection from an older dashboard page is still current.

## 9. `GET /v1/preferences`

Returns the account's complete `PreferenceSet`.

### Response: `200 OK`

```json
{
  "account_id": "acct_01K4A4ZMVN08VK0Y6FMV7D0SXC",
  "values": [
    "lowest_cost",
    "no_printer"
  ],
  "updated_at": "2026-09-04T16:08:12Z"
}
```

Both preference responses include the `account_id` derived from the authenticated principal; the
client never supplies it. The array uses the canonical order shown in the data-model preference
vocabulary. Its order does not indicate priority. A new account returns its `account_id` with an
empty array.

## 10. `PUT /v1/preferences`

Replaces the complete preference set. Partial preference patches are not supported in v1.

### Request

```json
{
  "values": [
    "lowest_cost",
    "no_printer"
  ]
}
```

Rules:

- `values` may be empty;
- values must be unique;
- unknown values fail the full request; and
- array order is ignored and normalized in the response.

### Response: `200 OK`

```json
{
  "account_id": "acct_01K4A4ZMVN08VK0Y6FMV7D0SXC",
  "values": [
    "lowest_cost",
    "no_printer"
  ],
  "updated_at": "2026-09-05T18:30:04Z"
}
```

## 11. `PUT /v1/items/{item_id}/return-summary`

Publishes a normalized state observed by the extension on the live retailer page. The body never
contains the agent's observation, raw page content, or a terminal artifact.

### Request

```json
{
  "state": "label_ready",
  "update_source": "extension_live_page",
  "handoff_evidence": null,
  "observed_at": "2026-09-05T18:41:09Z"
}
```

### Currently accepted transitions

| Current state | Requested state | Required source | Result |
|---|---|---|---|
| `not_started` | `in_progress` | `extension_live_page` | accepted |
| `not_started` | `qr_ready` | `extension_live_page` | accepted after live terminal-page validation |
| `not_started` | `label_ready` | `extension_live_page` | accepted after live terminal-page validation |
| `in_progress` | `in_progress` | `extension_live_page` | accepted as a repeatable logical refresh |
| `in_progress` | `qr_ready` | `extension_live_page` | accepted |
| `in_progress` | `label_ready` | `extension_live_page` | accepted |
| `qr_ready` | `qr_ready` | `extension_live_page` | accepted as a repeatable no-op |
| `label_ready` | `label_ready` | `extension_live_page` | accepted as a repeatable no-op |

For `qr_ready` and `label_ready`, `handoff_evidence` must be `null`. The extension publishes the
normalized outcome only after it has validated the live terminal page. It does not publish the QR
value, label bytes, barcode, address, or protected URL.

### Reserved but blocked transitions

| Requested state | Result |
|---|---|
| `handed_to_carrier` | `409 state_blocked` until `ARCH-B3` identifies the allowed publisher |
| `complete` | `409 state_blocked` until `ARCH-B8` defines its meaning and transitions |

`not_started` is server-created and cannot be requested through this endpoint. A direct transition
from `not_started` to a ready outcome allows the extension to publish a terminal page that it can
validate even when no earlier progress update reached the server. Backward transitions and
transitions between `qr_ready` and `label_ready` return `409 state_transition_not_allowed`.

This is only the minimum monotonic dashboard projection. It does not define resumption,
reconciliation, or recovery of interrupted browser workflows; those remain `ARCH-B1`.

### Response: `200 OK`

```json
{
  "state": "label_ready",
  "update_source": "extension_live_page",
  "handoff_evidence": null,
  "observed_at": "2026-09-05T18:41:09Z",
  "updated_at": "2026-09-05T18:41:10Z"
}
```

The server derives no carrier eligibility from `label_ready`. A printed UPS or FedEx label does not
make USPS pickup valid, and no pickup action is part of this contract.

## 12. `DELETE /v1/account`

Deletes the authenticated account and its active primary records. This is the baseline user-facing
deletion operation; backup expiry, recovery periods, and detailed retention remain `ARCH-B4`.

### Response: `204 No Content`

The response has no body. After success, the deleted account's authenticated session is invalidated
and its primary records are no longer available through the API.

Single-order deletion is not included because its retention and relational behavior remain
`ARCH-B4`.

## 13. UI handling requirements

The frontend and extension UI must handle these states without inventing product behavior:

- extension state: obtain it from the client-side extension integration and compose it locally; it
  is not a field in any server response.
- unknown deadline: show an unknown state; do not derive a deadline from delivery date in the
  browser.
- unknown fee: show “fee unknown”; do not render it as free.
- multiple currencies: render separate values; do not add them together.
- `qr_ready`: show that the retailer QR outcome is ready, but do not imply carrier pickup.
- `label_ready`: show that a printable label is ready, but do not imply it has USPS postage.
- unavailable next action: determine availability from local extension state rather than asking the
  server to infer it.
- `409 state_blocked`: keep the recorded current state and show a non-terminal explanation.

## 14. Contract fixtures and tests

The example response in section 7 is the canonical initial dashboard fixture. Frontend work may copy
it into a local mock without changing names or enum values.

Server tests should verify at minimum:

1. account scoping returns `404` for another account's item;
2. unknown request fields and enum values return `422`;
3. dashboard urgency is calculated from `metrics.as_of`, and item-detail urgency is calculated from
   `generated_at`;
4. every supported return-state and condition combination produces the `NextAction` code and
   canonical label in the normative derivation table, including `not_started` with `ineligible`,
   `not_started` with `expired`, unknown eligibility, and an unknown deadline;
5. `closing_soon_count` includes `days_remaining` values at `0` and the configured maximum and
   excludes values at `-1` and maximum plus one;
6. `closing_soon_count` includes unknown eligibility, excludes known-ineligible and unknown-deadline
   candidates, includes qualifying `qr_ready` and `label_ready` candidates, and is unaffected by
   price;
7. dashboard list filters do not change account-wide metrics;
8. currencies are aggregated separately;
9. preference reads and writes return the authenticated `account_id`, and updates enforce uniqueness
   and replace the complete set;
10. summary writes enforce the transition table and field invariants, including repeatable
    same-state `qr_ready` and `label_ready` publications;
11. `handed_to_carrier` and `complete` return `state_blocked` while their blockers remain open; and
12. responses and logs never contain raw DOM or protected terminal artifacts.

## 15. Deferred contracts

These require a new design decision or later-priority contract and must not be added ad hoc to v1:

| Area | Reason deferred |
|---|---|
| Google credential exchange and session transport | Authentication mechanism is not needed to freeze UI models |
| Order-page ingestion and normalization | Coupled to parsing and AI-pipeline work excluded from this contract |
| Interrupted-workflow recovery and reconciliation | `ARCH-B1` |
| Dashboard-to-extension commands | `ARCH-B6` |
| Carrier handoff write | `ARCH-B3` |
| `complete` transition | `ARCH-B8` |
| Single-order deletion and backup lifecycle | `ARCH-B4` |
| Calendar operations | Priority 2 |
| Carrier pickup operations | Requires separate carrier contract and USPS eligibility rules |

Once the frontend and server agree on this Markdown contract, an OpenAPI document and generated
language types may be added as derived artifacts. They must not expand scope or silently resolve any
deferred decision.
