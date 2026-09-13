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

- Google sign-in for the dashboard, and browser linking for the extension;
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
- error response shape;
- ownership and return-state validation rules, including the transition table in section 11, which
  gained the abandonment reset on 2026-09-13 and is otherwise closed. That addition only widens what
  is accepted; nothing previously accepted is now refused;
- the two-transport session posture in section 3.2 and the cross-origin rules in section 3.5. Section
  3.5 dropped an unimplementable double-submit-token requirement on 2026-09-13 and is otherwise
  closed. That removal narrows nothing a client relies on: no client ever sent such a token, because
  no document ever defined one to send;
- the existence, path, method and required caller of every authentication route in section 5,
  including the Google credential-exchange route; and
- the caller-enforcement rules in section 5.2.

The following are intentionally not frozen:

- request and response field names for the authentication routes in section 5.1, which are the one
  part of the stable surface still being written;
- credential, grant and pairing lifetimes, rate-limit values, and the concrete origin strings and
  preflight max-age in each environment's allowlist;
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

Every `/v1` route in this document requires an authenticated application principal, except the three
routes in section 5.1 that exist to establish one: the Google credential exchange, pairing creation,
and pairing redemption. The server maps a principal to an account using the Google `sub` identity
claim. Clients never submit an `account_id` to choose the account being accessed.

There are two client kinds and two transports, resolving to one principal model.

- **The dashboard** presents a first-party session cookie: `Secure`, `HttpOnly`, `SameSite=Lax`. It
  is not readable by page script, so a script-injection flaw on the dashboard can ride the session
  but cannot exfiltrate it. Because it is ambient, every mutating dashboard route additionally
  requires an `Origin` header matching the allowlist in section 3.5, and refuses the request when
  that header is absent or mismatched.
- **The extension** presents an opaque bearer credential in the `Authorization` header, obtained
  through the browser-linking flow in section 5.1. It is never ambient, so no request-forgery token
  is required on the extension leg and none is defined for it.

Both resolve to the same account principal and every route's authorization logic is identical
afterwards. The principal also carries its **client kind** — `dashboard` or `extension` — which
section 5.2 makes enforceable on the routes this contract restricts to one caller.

The extension has no relationship with Google. It holds no Google client, requests no scope, and
never sees an identity assertion; the only Google credential exchange in the system is the
dashboard's, in section 5.1. Frontend code should still put credential handling behind a single
client adapter, but the transport choice is frozen rather than deferred: it is not an implementation
detail either client may vary.

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

Responses that carry a credential — the redemption and refresh responses in section 5.1 — use
`Cache-Control: no-store` and are never held in page-reachable storage. In the extension they live
only where section 9 of the authentication design permits: the service worker.

### 3.5 Cross-origin and request forgery

The API is called from two browser origins and from nothing else.

| Leg | Origin | Credentials | Forgery defense |
|---|---|---|---|
| Dashboard to API | The dashboard's own origin for that environment | `Access-Control-Allow-Credentials: true` | `SameSite=Lax`, plus strict `Origin` matching on every mutating route, `DELETE /v1/account` included |
| Extension to API | `chrome-extension://<published extension id>` | **Not permitted.** The header is not sent for this origin | None required; the bearer credential is never ambient |

The rules:

- The allowlist is **exact and per-environment**. The production dashboard origin and the published
  extension ID in production; the development dashboard origin and the development extension ID in
  development. An unpacked development build gets a different ID unless its key is pinned, so the
  development allowlist must account for that.
- **No wildcard origin is ever emitted**, in any environment, on any route, for any client.
- `Vary: Origin` is sent on **every** response — success, error, and preflight — so an allowlist
  decision is never cached across origins.
- An origin absent from the allowlist is refused. It is not answered with a permissive header, and a
  simple request from it is not silently allowed by omitting the CORS headers.
- Credentials cross only on the dashboard origin. `Access-Control-Allow-Credentials` is never sent
  for the extension origin, because the extension leg does not need it and sending it is a
  liability.
- The extension leg is preflighted, because `Authorization` is not a safelisted request header.
  Preflight responses allow `authorization` and `content-type` and set an `Access-Control-Max-Age`
  long enough that a preflight is not paid per request.
- The concrete origin strings and the max-age value are environment configuration, not contract.

**`DELETE /v1/account` carries no separate forgery token, and an earlier revision of the table above
required one.** That revision said "plus a double-submit token on `DELETE /v1/account`" and never
defined it — no name, no attributes, no issuance point, no comparison rule — which is not a
requirement an implementer can satisfy without inventing one. It is dropped rather than specified,
for two reasons that are worth stating because the omission looks like a weakening and is not.

The first is mechanical. A double-submit token has to be readable by page script in order to be
copied into a header or a body, which means a second cookie without `HttpOnly`. Section 3.2's
session posture is built on the opposite property: the session cookie is not readable by page
script, so a script-injection flaw on the dashboard can ride the session but cannot exfiltrate it.
Introducing a script-readable companion cookie on the same origin to protect one route trades that
property for a control the route already has.

The second is that the control it already has is the stronger one. Strict `Origin` matching refuses
the request when the header is absent or mismatched, and `Origin` is set by the browser and is
forbidden to page script, so a cross-site attacker cannot produce a matching one. Double-submit,
by contrast, is defeated by an attacker who can write a cookie on the registrable domain — and this
design's `SameSite=Lax` posture *requires* the dashboard origin and the API origin to share a
registrable domain, which is precisely the configuration in which a sibling host makes double-submit
weakest. Adding it would have bought no coverage that `Origin` matching does not already give, in
exchange for a second cookie and a weaker session property.

Irreversibility is a reason for care on this route, and section 5.2 already answers it in the place
where it belongs: `DELETE /v1/account` requires a dashboard principal, so a stolen extension
credential cannot reach it at all. The forgery defense on this route is `SameSite=Lax` plus strict
`Origin` matching, identical to every other mutating dashboard route. If a future review wants
belt-and-braces here, it is a new decision that must specify the cookie concretely, not a sentence
reinstated.

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

### 4.1 The `401` discriminator

`reason` is a closed v1 enum and adding a value to it is a breaking change, so every authentication
failure keeps `unauthenticated`. But a client cannot behave correctly without knowing *which*
authentication failure it was — a refreshable expiry and a revoked grant demand opposite responses —
so the discriminator travels in `details`:

```json
{
  "reason": "unauthenticated",
  "message": "Sign in again to continue.",
  "request_id": "req_01K4A6W0K45P8N9FQF5A7B3C2D",
  "details": {
    "auth_reason": "grant_revoked"
  }
}
```

**The required behaviour is per principal, not universal.** The two client kinds have different
recovery paths available to them — the extension can refresh and the dashboard cannot, the extension
has local records to clear and the dashboard has none — so a single instruction cannot be correct for
both. Each row below states who can receive the value and what each recipient does.

| `details.auth_reason` | Who can receive it | Meaning | Required behaviour, by principal |
|---|---|---|---|
| `credential_expired` | **Extension only** | The access credential is past its lifetime; the grant is still live | **Extension:** refresh once via `POST /v1/auth/refresh`, then retry the call exactly once. **Dashboard:** not reachable — see the two paragraphs below this table |
| `grant_revoked` | Extension or dashboard | The grant is gone — disconnected from the linked-browsers list, dashboard sign-out anywhere on the account, refresh reuse detected, or an idle or absolute limit reached | **Extension:** clear the credential and the local workflow records, render as not linked, do not retry. **Dashboard:** the session is over. Discard any client-side view of it, render signed out, and offer sign-in through `POST /v1/auth/google`. Do not retry, and do not attempt a refresh — there is none on this leg. The dashboard cannot clear its own cookie, which is `HttpOnly`; the server clears it on the response that carries this discriminator |
| `account_deleted` | **Nobody.** Reserved and unreachable in v1 | Account deletion removes the account's grant and credential rows, so there is nothing left to resolve a presented credential against and the server answers `not_linked` instead (section 12) | None in v1. A client must still tolerate the value, and it stays in this closed set because removing a value from a closed set is itself a breaking change |
| `not_linked` | Extension or dashboard | Two situations the server cannot tell apart, and does not try: no credential was presented, or a credential was presented and resolves to no grant — revoked and reaped, never valid, or deleted with the account | **Extension:** branch on whether this client presented a credential, which it knows from its own storage and the server does not. Presented none: offer the linking flow, clear nothing, do not retry. Presented one: this is terminal — clear the credential, the local workflow records **and any checkpoints**, render as not linked, do not retry. **Dashboard:** there is no linking flow on this leg and nothing local to clear. Either way it is signed out; render the signed-out state and offer sign-in through `POST /v1/auth/google`. Do not retry |
| `wrong_client_kind` | Extension or dashboard | The principal is valid but the route is restricted to the other client kind | Both: do not retry. This is a client defect, not a credential problem, and no credential operation fixes it |

**`credential_expired` is extension-only, and an earlier revision of this table did not say so.** That
revision gave one universal instruction — "Refresh once, then retry the call exactly once" — to every
client receiving the value. A dashboard principal cannot follow it. Section 5.2 restricts
`POST /v1/auth/refresh` to an extension principal in as many words, and this contract defines no other
refresh path for any leg, so the guidance told one of the two principals to perform an operation the
same contract forbids it. That was an instruction no dashboard implementation could carry out, not
merely an imprecise one.

It is corrected by narrowing the value rather than by inventing a route, and the narrowing follows from
what a refresh credential is for. `credential_expired` describes one specific state: the access
credential has passed its own lifetime while the grant behind it is still live. That state is only
worth representing when something can act on it, and the only thing that can is a refresh — which is
why an extension's access credential is deliberately short-lived and its grant long-lived. A dashboard
grant has no refresh credential and no route that would accept one, so a dashboard access credential
shorter-lived than its own grant would end the session with no way to continue it. It is therefore not
minted that way: **a dashboard access credential's lifetime is the dashboard grant's lifetime**, and
the session's duration is governed by the grant's idle and absolute limits rather than by a separate
credential clock. This is a constraint on configuration, and it belongs with the other authentication
numbers under `ARCH-B4`; like the coarsening-interval constraint recorded there, it must be enforced by
a configuration check rather than by a reviewer's memory.

The consequence is that the "credential expired, grant still live" state has no dashboard instance to
describe. The resolution order is unchanged and is stated once, normatively, in
[`boomerang-auth-open-decisions.md`](boomerang-auth-open-decisions.md) section 5.3; this section adds
no case to it and removes none. A dashboard session that has run out resolves through the rows that
already cover it — `grant_revoked` while the grant row is still present and past a limit or revoked,
and `not_linked` once nothing resolves at all — and the dashboard's recovery under both is the path it
already has: sign in again through `POST /v1/auth/google`, which is a fresh credential exchange rather
than a renewal. This adds no route, no schema column and no wire surface. The alternative reading —
that dashboard sessions are refreshed by some mechanism — was never written down anywhere, and writing
it down would have meant designing a route no accepted document enumerates.

One consequence is worth naming rather than discovering: signing in again mints a new dashboard grant
rather than reviving the old one, so the stale grant lingers until its own limits pass. That is
correctness-neutral. `GET /v1/auth/grants` is extension-kind only (section 5.1), so a stale dashboard
grant is never shown to the user as a linked browser, and every predicate that resolves a credential
evaluates expiry at read time.

`details.auth_reason` is a closed set within v1 — `account_deleted` included, which is why it is
marked reserved above rather than deleted — and it is the only authentication field that ever
appears in `details`. A credential, a refresh credential, a grant identifier, a pairing identifier, a
verifier, a short code, or a Google subject must never appear there; section 4's prohibition on
tokens in `details` is unchanged and absolute.

`wrong_client_kind` is carried on a `401` rather than a `403` because `reason` has no `forbidden`
value and adding one would be a breaking change. That is a deliberate accommodation of the closed
enum, not a claim that the credential was invalid.

## 5. Endpoint summary

The `Caller` column is **enforced**, not descriptive. Section 5.2 states how.

| Method | Path | Caller | Purpose |
|---|---|---|---|
| `POST` | `/v1/auth/google` | Dashboard only | Exchange a Google identity assertion for the dashboard session cookie |
| `POST` | `/v1/auth/pairings` | Extension only | Start a browser-linking pairing from a challenge |
| `POST` | `/v1/auth/pairings/{pairing_id}/approve` | Dashboard only | Bind a pending pairing to the signed-in account |
| `POST` | `/v1/auth/pairings/{pairing_id}/redeem` | Extension only | Poll, and on approval redeem the pairing with the verifier for a credential pair |
| `POST` | `/v1/auth/refresh` | Extension only | Rotate the refresh credential and mint a new access credential |
| `GET` | `/v1/auth/grants` | Dashboard only | The linked-browsers list |
| `POST` | `/v1/auth/grants/revoke` | Dashboard or extension | Revoke a grant |
| `GET` | `/v1/me` | Dashboard or extension | Current account profile |
| `GET` | `/v1/dashboard` | Dashboard or extension | Metrics, urgency legend, candidates, and pagination |
| `GET` | `/v1/items/{item_id}` | Dashboard or extension | One return-candidate detail |
| `GET` | `/v1/preferences` | Dashboard or extension | Current preference set |
| `PUT` | `/v1/preferences` | Dashboard or extension | Replace preference set |
| `PUT` | `/v1/items/{item_id}/return-summary` | **Extension only** | Publish a supported normalized state |
| `DELETE` | `/v1/account` | **Dashboard only** | Delete the active account and primary records |

### 5.1 Authentication routes

Extension-to-server authentication is decided: server-brokered browser linking with proof-of-key
redemption, a bearer credential on the extension leg, a first-party cookie on the dashboard leg. The
mechanism is specified in
[`boomerang-extension-auth-proposal.md`](boomerang-extension-auth-proposal.md), sections 6, 8, 9 and
10, which is normative. This section freezes the wire surface and the invariants; it does not
restate the mechanism.

Request and response **field names for these seven routes are not yet frozen** (section 2). The
routes, their callers, and the rules below are.

**`POST /v1/auth/google` — dashboard only, unauthenticated.** Takes a Google identity assertion and
sets the session cookie on the response. This is the only place in the system where a Google
assertion is verified and the dashboard is its only caller. Issuer, audience, signature and expiry
are all checked; a missing `sub` claim is a refusal. The `sub` claim is never returned, never
logged, and never placed in `details`. The identity scope is basic identity and nothing else — no
Gmail, no Calendar, no retailer access — and no route in this contract ever widens it.

**`POST /v1/auth/pairings` — extension only, unauthenticated.** Takes the challenge derived from a
verifier that never leaves the extension. Returns a pairing identifier, a short human-readable code,
an expiry a few minutes out, and a polling interval. Nothing is bound to an account yet.
Rate-limited; the ceiling returns `429 rate_limited`.

**`POST /v1/auth/pairings/{pairing_id}/approve` — dashboard only, authenticated.** Binds the pairing
to the account signed into the dashboard at that moment. The account is never taken from the
request. There is no route, and never will be, that lets a caller type a code in from elsewhere: the
only path to approval is the link the extension itself opened.

**`POST /v1/auth/pairings/{pairing_id}/redeem` — extension only, unauthenticated.** Takes the
verifier. Before approval it returns a pending result, which the extension polls on the interval it
was given. On the first poll after approval it returns an opaque access credential and an opaque
refresh credential, exactly once, and consumes the pairing. A consumed or expired pairing can never
be redeemed again. Rate-limited.

**`POST /v1/auth/refresh` — extension only.** Authenticated by the refresh credential, not by the
access credential. It rotates: the presented refresh credential is invalid immediately afterwards.
Presenting a rotated-away refresh credential revokes the entire chain of credentials descended from
that grant and returns `401` with `details.auth_reason` of `grant_revoked`. Rate-limited.

**`GET /v1/auth/grants` — dashboard only.** One entry per live **extension-kind** grant on the
account, with its creation time, last-use time, and human-readable browser label, so an approval is
discoverable and reversible rather than silent. It carries no credential material of any kind.

The client-kind filter is not a detail. This route is described elsewhere in this contract, and in
the dashboard UI, as *the linked-browsers list*, and an earlier revision of this paragraph said
“one entry per live grant on the account.” Those two descriptions diverge as soon as a dashboard
session is itself a grant, which it is under section 3.2's one-grant-model: unfiltered, the route
would return the caller's own dashboard session as though it were a linked browser, offer a
disconnect control against it, and let a user revoke their own session from a list that claims to be
about the extension. Extension-kind only, so the route and the list describe the same set.

**`POST /v1/auth/grants/revoke` — dashboard or extension.** The dashboard may revoke any grant on
the account; an extension principal may revoke only its own. Revocation takes effect immediately,
not at the next expiry.

Invariants across all of them:

- Access credentials are **opaque** and resolved against a server-side grant record on every
  request. They are not self-contained signed tokens, because revocation has to take effect
  immediately and provably.
- No credential, grant identifier, pairing identifier, verifier, challenge or short code ever
  appears in a log line, an error `message`, an error `details` object, or any other route's
  response body.
- No response elsewhere in this document gains a credential, grant or pairing field. Extension
  connection state stays composed client-side exactly as section 7 says; under this scheme its
  definition is "this browser holds a valid grant for this account."
- Concrete lifetimes and rate-limit values are not set here. They are `ARCH-B4`.

**One thing this contract does not yet answer, named so it is not discovered late.** This contract
enumerates no dashboard sign-out route; the low-level design carries an `end_session` interface with
no route behind it, and the route's wire shape is still unwritten.

Its *behaviour*, which was the open part, is now decided. Dashboard sign-out revokes **every live
extension grant on the account**, not only the grant linked from the browser being signed out from
— the user's call on 2026-09-13, recorded as `MIG-19`. An earlier revision of this paragraph said
the revocation was scoped to the same browser and that a browser or session correlator on both the
grant and the pairing record was *required by the accepted decision and its design open*. That is
superseded: no correlator ships, in any form, so there is nothing open about it and nothing for this
contract to reserve. The reasoning is in
[`boomerang-auth-open-decisions.md`](boomerang-auth-open-decisions.md), section 2.4 — every ordinary
failure of a correlator is a silent fail-open, which is the one direction the decision was meant to
protect.

None of that is visible on the wire. The scope lives in a single service-layer operation,
`revoke_grants_for_sign_out(account_id)`, which already defaults to account-wide; no route, no
request or response shape, and no discriminator changes. A revoked extension sees exactly what an
explicit disconnect produces: `401` with `details.auth_reason` of `grant_revoked`, per section 4.1.

### 5.2 Caller enforcement

The principal carries its client kind (section 3.2), and the server checks it before the route's own
logic runs. A principal of the wrong kind returns `401 unauthenticated` with `details.auth_reason`
of `wrong_client_kind` (section 4.1).

| Route | Required client kind | Why |
|---|---|---|
| `PUT /v1/items/{item_id}/return-summary` | Extension | Only the extension observes a live retailer page, and only it can confirm a run is abandoned. A dashboard principal has nothing to publish from, and this covers the abandonment reset in section 11 |
| `DELETE /v1/account` | Dashboard | Irreversible. A stolen extension credential must not be able to destroy the account |
| `POST /v1/auth/pairings/{pairing_id}/approve` | Dashboard | Approval is the human act that binds a browser to an account |
| `GET /v1/auth/grants` | Dashboard | The linked-browsers list is administration, not workflow |
| `POST /v1/auth/refresh` | Extension | A dashboard session is not refreshed this way, and there is no other way — this contract defines no refresh path for the dashboard leg, which is why `credential_expired` is extension-only in section 4.1. A dashboard session that has run out is re-established through `POST /v1/auth/google` |

Routes whose caller is "Dashboard or extension" accept either kind and are unchanged by this
section. `POST /v1/auth/grants/revoke` accepts either, but an extension principal may revoke only
its own grant; any other grant identifier returns `404 not_found`, consistent with section 3.2.

The three unauthenticated routes — `POST /v1/auth/google`, `POST /v1/auth/pairings` and
`POST /v1/auth/pairings/{pairing_id}/redeem` — carry no principal, so there is no client kind to
check. Their `Caller` column is constrained only by the cross-origin allowlist in section 3.5 and by
the mechanism itself: without the verifier, a pairing cannot be redeemed by anyone. That is a real
limit on what "enforced" means for those three, and it is stated rather than glossed.

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

An item reset to `not_started` by the abandonment reset in section 11 leaves `in_progress_count` at
the next calculation and keeps contributing to `closing_soon_count` on the same predicate as any
other unstarted return.

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
| `in_progress` | `not_started` | `user_confirmed` | accepted only as the abandonment reset below |
| `not_started` | `not_started` | `user_confirmed` | accepted as the idempotent repeat of that reset |

For `qr_ready` and `label_ready`, `handoff_evidence` must be `null`. The extension publishes the
normalized outcome only after it has validated the live terminal page. It does not publish the QR
value, label bytes, barcode, address, or protected URL.

### The abandonment reset

A run that ends without an outcome — the user closes the tab, the page diverges, the service worker
is evicted, the user simply gives up — leaves the summary in `in_progress` with no way out. The
dashboard then derives the continue-return action forever on an item whose tab, workflow record and
checkpoint no longer exist, and `in_progress_count` is permanently wrong. The transition back is the
`ARCH-B1` sub-decision recorded in
[`../plan/boomerang-decisions.md`](../plan/boomerang-decisions.md), and it is the only exit.

The extension publishes the reset after the user has confirmed the run is abandoned and after it has
discarded its own workflow record and checkpoint for the item. The server accepts it only when all of
the following hold:

1. the principal is an extension principal (section 5.2); a dashboard principal is refused with
   `wrong_client_kind`;
2. `update_source` is exactly `user_confirmed`. A `not_started` request carrying
   `extension_live_page` is refused with `409 state_transition_not_allowed`, because a page
   observation may never move an item backward;
3. the stored state is `in_progress`, read and compared in the same transaction as the write, so the
   check is a compare-and-set rather than a read followed by a hopeful update;
4. `handoff_evidence` is `null`; and
5. `observed_at` is at or after the stored summary's `observed_at`. A tab suspended before a newer
   run began cannot rewind that newer run when it wakes.

The server can verify four of these. It cannot verify that the user actually confirmed anything; that
is a client obligation, and it is written here as one rather than assumed. What bounds the damage if
a client ignores it is the rest of the list: a reset reaches only items inside the caller's own
account, only from `in_progress`, and it destroys nothing. `not_started` is the state the item would
have held had the run never started, and the summary carries no artifact, no evidence and no history
to lose. A reset discards a claim about an abandoned run, not user data.

**Idempotency.** A reset whose response is lost may be retried unchanged. The retry finds the summary
already in `not_started` and returns `200` with the stored row. That is what the second new table row
is: one capability expressed as the transition and its own retry, not two capabilities.

**Racing a live publication from another tab.** Ordering is decided by the compare-and-set in
precondition 3, and the bias is always toward the real outcome:

- reset first, then `qr_ready` or `label_ready` from the other tab — accepted, because `not_started`
  to a ready outcome is already an accepted transition. The outcome wins;
- `qr_ready` or `label_ready` first, then the reset — refused with
  `409 state_transition_not_allowed`, because the stored state is no longer `in_progress`. The
  outcome wins again;
- reset first, then an `in_progress` refresh from the other tab — accepted; the live run
  re-establishes itself and the continue action returns;
- an `in_progress` refresh first, then a reset whose `observed_at` predates it — refused by
  precondition 5.

A reset can therefore never destroy a terminal outcome. A client treats `409` on a reset as
information rather than failure: something else has already moved the item, and the item is no longer
stranded.

**Effect on the metrics.** The item leaves `in_progress_count` at the next calculation, which is the
count the strand was corrupting. `closing_soon_count` is deliberately unchanged in either direction:
its predicate excludes only `handed_to_carrier` and `complete` (section 7), and abandoning a run does
not make the return less due. The item returns to the `start_return` next action by the data model's
ordinary precedence, because that is now what it is — a return the user has not started.

**What this does not reach.** The reset requires a live extension grant, so it does not cover an
abandonment whose trigger is the loss of that grant: dashboard sign-out, disconnection from the
linked-browsers list, or account deletion. A revoked extension cannot publish anything, and after
re-linking it has already cleared the local workflow records that would tell it which items were
stranded. Those items stay stranded, and that residual remains inside `ARCH-B1`.

The sign-out trigger is **account-wide**, and that is worth stating rather than leaving to be
inferred from the scope in section 5.1. Signing out on one machine revokes every linked browser's
grant, so it strands the half-finished returns in all of them at once, not only in the browser the
user signed out from — including browsers that user is not looking at. Each stranded item's stored
state stays where the run left it and its next action is derived forever. The only mitigation in v1
is a dashboard one and needs nothing from this contract: the sign-out confirmation warns when
`in_progress_count` is non-zero, from the value the dashboard aggregate already returns.

### Reserved but blocked transitions

| Requested state | Result |
|---|---|
| `handed_to_carrier` | `409 state_blocked` until `ARCH-B3` identifies the allowed publisher |
| `complete` | `409 state_blocked` until `ARCH-B8` defines its meaning and transitions |

`not_started` is server-created, and the abandonment reset above is the single exception: it is the
only way a client may request that state, and only under the preconditions listed there. A direct
transition from `not_started` to a ready outcome allows the extension to publish a terminal page
that it can validate even when no earlier progress update reached the server. Every other backward
transition, and transitions between `qr_ready` and `label_ready`, return
`409 state_transition_not_allowed`.

Monotonicity is relaxed here, not abandoned. Exactly one backward edge exists; it requires an
explicit user act carried by `user_confirmed`; and no `extension_live_page` observation can move an
item backward from any state, which is the property the rule existed to protect. This is still only
the minimum dashboard projection. It does not define resumption, reconciliation, or recovery of
interrupted browser workflows; those remain `ARCH-B1`, of which the abandonment reset is now a
closed sub-decision.

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

This route requires a dashboard principal (section 5.2). A stolen extension credential cannot
destroy the account.

### Response: `204 No Content`

The response has no body. After success the deleted account's primary records are no longer
available through the API.

**Every grant for the account, in every client, is revoked synchronously before the `204` is
returned** — not on a later sweep, not at the next expiry. That covers the dashboard session and
every extension grant in every linked browser. Any subsequent call from any of them returns
`401 unauthenticated` with `details.auth_reason` of `not_linked`.

An earlier revision of this section promised `account_deleted` there. That was wrong as written, and
not merely imprecise: the same deletion this section requires removes the account's grant and
credential rows, so a credential presented afterwards resolves against nothing and there is no row
left to carry the distinction. No implementation that performs the deletion can return the
discriminator, and the project declined to build a credential tombstone to preserve it — a durable
artifact surviving a deletion the product calls a deletion is the wrong trade for a single enum
value. `account_deleted` is therefore **reserved and unreachable in v1**. It stays in the published
`details.auth_reason` enum rather than being removed, because removing a value from a closed set is
itself the breaking change the closed set exists to prevent.

The distinction is not lost; it moves to the only party that still holds it. The extension knows
whether *it* presented a credential, from its own storage, and selects its cleanup branch on that
fact (section 4.1). Having presented none, it is an unlinked install: it offers the linking flow and
clears nothing. Having presented one, this is terminal — whatever this browser was linked to no
longer exists — and it clears the credential, the local workflow records and the checkpoints, renders
as not linked, and does not retry. The server cannot recover that fact after deletion and stores
nothing in order to. What is genuinely given up is message precision: the extension can no longer
tell “your account was deleted” from “this browser's link was revoked or reaped” when composing its
empty state, and *this browser is no longer linked to Boomerang* is the truthful message under both.

The extension half of the cleanup is best-effort by nature. An extension learns of the deletion only
on its next call, and clears its credential, its local workflow records and its checkpoints then —
records that now reference identifiers which no longer exist. If that browser is never opened again,
that never happens. The residual is stated rather than solved.

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
- `401 unauthenticated`: branch on `details.auth_reason` per section 4.1, **and branch on which client
  you are**, because the two legs have different recovery paths and the same discriminator means
  different work in each. In the extension: a refreshable expiry is not a sign-out and must not be
  shown as one, and `credential_expired` is the only value that leads to a refresh; a revoked grant
  clears the extension's credential and its local workflow records together. `not_linked` is two states
  wearing one name, and only the client can separate them: if the extension presented no credential it
  offers the linking flow and clears nothing, and if it presented one the link is gone — revoked,
  reaped, or deleted with the account — and it clears the credential, the local workflow records and
  the checkpoints together and renders as not linked. The empty state must be truthful under every one
  of those causes, which means it must not claim the account was deleted: the server no longer says
  that and cannot (section 12). *This browser is no longer linked to Boomerang* is accurate in all of
  them. In the dashboard: there is no refresh and no linking flow, so every `401` on this leg is the
  same user-visible event — the session is over. Render the signed-out state and offer sign-in through
  `POST /v1/auth/google`. The dashboard must not attempt a refresh on `credential_expired`, which it
  cannot receive, and must not attempt one on any other value either; and it must not offer to "link
  this browser", which is extension copy and means nothing on the dashboard.

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
11. `handed_to_carrier` and `complete` return `state_blocked` while their blockers remain open;
12. responses and logs never contain raw DOM or protected terminal artifacts;
13. an extension-origin preflight is answered with that exact origin allowed and **without**
    `Access-Control-Allow-Credentials`, and every response carries `Vary: Origin`;
14. an origin absent from the allowlist is refused, and no response ever carries a wildcard origin;
15. a mutating dashboard route refuses a request whose `Origin` header is absent or mismatched;
16. a bearer credential minted for one account cannot read another account's item;
17. a revoked grant is refused, and a rotated-away refresh credential revokes the whole chain
    descended from its grant;
18. account deletion revokes every grant for the account, in every client, before the `204` is
    returned; and
19. summary publication refuses a dashboard principal and account deletion refuses an extension
    principal, each carrying the discriminator in `details` and neither introducing a new `reason`
    value;
20. an abandonment reset is accepted from `in_progress` only with `user_confirmed`, is refused with
    `state_transition_not_allowed` when it carries `extension_live_page`, when the stored state is
    `qr_ready` or `label_ready`, or when its `observed_at` predates the stored `observed_at`, and is
    refused with the `wrong_client_kind` discriminator for a dashboard principal;
21. a repeated abandonment reset returns `200` with the stored `not_started` row rather than a
    conflict; and
22. a reset removes the item from `in_progress_count`, leaves `closing_soon_count` unchanged, and
    returns the item's next action to `start_return`; and
23. a call from a previously linked extension, made after its account was deleted, returns `401`
    with `details.auth_reason` of `not_linked` — never `account_deleted`, which no implementation
    that performs the deletion in section 12 can produce;
24. no response to a dashboard principal ever carries `details.auth_reason` of `credential_expired`,
    and a configuration in which a dashboard access credential's lifetime is shorter than its grant's
    fails validation rather than starting — the two together are what make the extension-only claim in
    section 4.1 true rather than aspirational; and
25. `DELETE /v1/account` is refused when its `Origin` header is absent or mismatched, and is accepted
    on a matching `Origin` with no forgery token of any kind presented, so that the removal of the
    unspecified double-submit token in section 3.5 is asserted rather than assumed.

## 15. Deferred contracts

These require a new design decision or later-priority contract and must not be added ad hoc to v1:

| Area | Reason deferred |
|---|---|
| Credential, grant and pairing lifetimes and rate-limit values | `ARCH-B4`. The authentication shape is frozen in sections 3.2, 3.5 and 5.1; only the numbers are open |
| Dashboard sign-out route | Only the route's wire shape is deferred; no document enumerates it yet. Its behaviour is decided: sign-out revokes every live extension grant on the account, behind one service-layer seam and with no wire change (`MIG-19`; see section 5.1). The browser correlator that this row previously named as required-and-unspecified **does not ship in any form** and is no longer deferred work — it is declined |
| Order-page ingestion and normalization | Coupled to parsing and AI-pipeline work excluded from this contract |
| Interrupted-workflow recovery and reconciliation | `ARCH-B1`, except the abandonment reset in section 11, which that gate decided on 2026-09-13 |
| Dashboard-to-extension commands | `ARCH-B6` |
| Carrier handoff write | `ARCH-B3` |
| `complete` transition | `ARCH-B8` |
| Single-order deletion and backup lifecycle | `ARCH-B4` |
| Calendar operations | Priority 2 |
| Carrier pickup operations | Requires separate carrier contract and USPS eligibility rules |

Once the frontend and server agree on this Markdown contract, an OpenAPI document and generated
language types may be added as derived artifacts. They must not expand scope or silently resolve any
deferred decision.
