# Boomerang — The Authentication Wire Format

## Status

This document freezes the request and response field names, types, nullability and status codes for
the seven authentication routes enumerated in
[`boomerang-api-contract.md`](boomerang-api-contract.md) section 5, together with the two vocabularies
those routes carry that no accepted document has yet defined — the browser-label platform token and
the pairing short code — and the response headers each route must emit.

It exists because the contract freezes those seven routes, their callers, their resolution order and
their invariants, and then says in as many words that their **field names are not frozen** (section
2, and again in section 5.1). Several implementers are about to build these routes at the same time.
Left as it is, each one invents a JSON vocabulary, the extension and the dashboard are written
against whichever lands first, and the contract's own stability boundary — which promises that
request and response field names are stable for parallel v1 implementation — is true of every route
in the system except the seven that establish the principal every other route depends on.

**What this document does not do.** It does not restate the pairing or rotation mechanism; that is
[`boomerang-extension-auth-proposal.md`](boomerang-extension-auth-proposal.md) sections 6, 8, 9 and
10, which is normative. It does not restate the credential resolution order; that is
[`boomerang-auth-open-decisions.md`](boomerang-auth-open-decisions.md) section 5.3, which is
normative and which supersedes the table in
[`boomerang-pairing-persistence.md`](boomerang-pairing-persistence.md) section 10. It does not
change the schema: `server/app/db/models.py` is built, is correct, and there is no migration tooling
in this repository, so a wire format that implies a schema change is a wire format that cannot ship.
Everything below fits the shipped tables.

It also invents **no authentication numbers**. Every lifetime, limit, interval and ceiling on these
routes is configuration under `ARCH-B4`, and the open-decisions ruling forbids inventing them. This
document freezes *shapes*: where a number travels on the wire, the field that carries it is named
here and its value comes from configuration.

Where this document contradicts the persistence proposal it follows the open-decisions rulings, which
are the rulings against that proposal. Where it contradicts nothing and simply decides, the decision
and its rejected alternatives are written out, so a later reader can reconstruct the reasoning rather
than guess at it.

---

## 1. Conventions inherited, not re-decided

These come from [`boomerang-data-model.md`](boomerang-data-model.md) section 3 and the contract's
section 3, and every shape below obeys them. They are listed because the point of this document is
that a second style must not appear.

- **Field names are `snake_case`.** No camelCase anywhere, in any direction.
- **Identifiers are opaque, case-sensitive strings.** Clients must not parse them. Example values in
  this document carry readable prefixes to make fixtures legible, exactly as the data model permits;
  the prefixes are not a contract.
- **A field naming another entity's identifier is `<entity>_id`** — `pairing_id`, `grant_id`,
  `account_id`. The bare `id` form is reserved for a response that *is* the entity, as in
  `GET /v1/me`. None of the seven responses below is a resource document, so none of them uses bare
  `id`.
- **Timestamps are RFC 3339 UTC instants**, `2026-09-05T18:22:41Z`. Never a Unix epoch, never a local
  offset, and never a duration where an instant will do. This is why no response below carries an
  OAuth-style `expires_in`.
- **A timestamp field is `<verb>_at`.** `expires_at`, `approved_at`, `created_at`, `last_used_at` —
  matching the column names on the shipped tables, which is not a coincidence worth breaking.
- **Durations, where one is genuinely a duration rather than an instant, are `<name>_seconds`** and
  are integers. One field in this document is a duration: `poll_interval_seconds`, which is an
  interval rather than a point in time and would be actively wrong as a timestamp.
- **Request objects reject unknown fields with `422 validation_failed`** (contract section 3.1).
  Every request model below is closed. This matters more here than elsewhere: an implementer who
  guesses `access_token` and gets a `422` learns immediately, which is the whole point of the rule.
- **Response objects may gain optional fields within v1**, and clients must ignore fields they do not
  understand.
- **The error envelope is `reason`, `message`, `request_id`, `details`**, exactly as
  `server/app/api/errors.py` builds it, and no route below constructs an error response of its own.

One more convention, which this document establishes rather than inherits, because the accepted
documents are consistent about it in prose and have never had to be consistent about it in JSON:

- **The system's own bearer credentials are called *credentials*, never *tokens*.** The contract, the
  proposal and the persistence document all say "access credential" and "refresh credential", and
  they do so deliberately: these are opaque strings resolved against a server-side row, not
  self-contained signed tokens, and the proposal's section 10 turns on that distinction. The wire
  format follows the prose. `access_credential` and `refresh_credential`, never `access_token`,
  `refresh_token` or `token_type`. The one field on these seven routes that *is* a token is Google's,
  and it is named so that its provenance is unmistakable.

---

## 2. What never appears on the wire

Before the shapes, the exclusions, because the shapes are partly defined by them. Section 5.1 of the
contract and section 4.1's closing paragraph already forbid most of this; it is collected here so
that an implementer building a response model has one list to check against.

The following exist in the database or in the request and **must never appear in any response body,
in any `details` object, in any log line, or in any header**:

| Value | Where it lives | Why it never surfaces |
|---|---|---|
| `accounts.google_subject` | Row | Contract section 3.2 and 5.1. `server/app/routes/me.py` keeps it off the wire by not listing it in the response model, and that is the pattern every model below follows |
| `auth_credentials.credential_hash` | Row | A digest of a live credential. Nothing outside the resolver ever reads it |
| `auth_credentials.generation` | Row | Reuse-detection bookkeeping. Exposing it would let a holder reason about rotation history |
| `auth_credentials.id` | Row | The credential row's identity is not an addressing value for any client; the grant is |
| `pairing_requests.code_challenge` | Row | Returning it would let anyone holding the pairing identifier confirm a guessed verifier offline |
| The presented `code_verifier` | Request | Never stored in any form, never logged, never echoed |
| The presented `platform_token` | Request | Read, mapped, discarded. Only the mapped enum member is stored — see section 5 |
| `auth_grants.revoked_reason` | Row | It is operational cause, not client-actionable state. The client learns `grant_revoked` from `details.auth_reason` and that is the whole of what it can act on |
| `auth_grants.idle_expires_at` / `absolute_expires_at` | Row | See section 7.6 — deliberately excluded, with the residual named |
| The pairing's `account_id` | Row | The dashboard already knows its own account; the extension must never learn one from a pairing |

And the standing prohibition, restated because it is the one an implementer is most likely to
violate while debugging: **no credential, refresh credential, grant identifier, pairing identifier,
verifier, challenge or short code ever appears in an error `message`, an error `details` object, or a
log line.** The only authentication field that ever appears in `details` is `auth_reason`.

---

## 3. The seven routes

Each route below gives the request shape, the response shape, the field table, and a worked example.
Every example value is an obvious placeholder. **No example in this document contains, or is derived
from, a real credential, token or secret**, and an implementer copying one into a fixture is copying
a string that cannot authenticate anything.

Every request model is closed to unknown fields. Every response is a dedicated Pydantic model in the
style of `server/app/routes/me.py` — never an ORM row, because the row is a storage mapping and the
wire shape is a contract, and the two are allowed to drift.

### 3.1 `POST /v1/auth/google` — Google assertion exchange

Dashboard only, unauthenticated. The only place in the system where a Google assertion is verified.

#### Request

| Field | Type | Required | Null allowed | Notes |
|---|---|---|---|---|
| `google_id_token` | string | yes | no | The Google identity assertion, verbatim as the Google Identity Services callback delivered it. Non-empty |

```json
{
  "google_id_token": "EXAMPLE-GOOGLE-ID-TOKEN-NOT-A-REAL-VALUE"
}
```

**Why `google_id_token`.** Three names were available and two were rejected. `credential` is what
Google's own `CredentialResponse` calls this field, and it is precisely the word this system reserves
for its own opaque bearer strings — using it here would mean the word "credential" refers to a
Google-issued JWT on one route and a Boomerang-issued opaque string on two others, which is the
second vocabulary this document exists to prevent. `id_token` is accurate but unattributed, and this
system has exactly one relationship with an identity provider and should say so at the field. The
frozen name states both what the value is and whose it is, and it cannot be mistaken for anything
Boomerang mints.

The request carries nothing else. It carries no `account_id` — the contract's section 3.2 forbids a
client choosing the account. It carries no nonce echo, no `client_id` and no redirect: the audience
and issuer checks are server-side configuration, and a client-supplied `client_id` would be a value
the server must ignore, which is worse than a value that does not exist.

#### Response: `200 OK`

The response sets the session cookie (section 8) and returns the signed-in account's profile, using
**the same field names as `GET /v1/me`**.

| Field | Type | Null allowed | Notes |
|---|---|---|---|
| `id` | string | no | The account identifier |
| `email` | string | yes | |
| `display_name` | string | yes | |
| `avatar_url` | string | yes | |

```json
{
  "id": "acct_01K4A4ZMVN08VK0Y6FMV7D0SXC",
  "email": "sam@example.com",
  "display_name": "Sam",
  "avatar_url": "https://example.com/avatar.png"
}
```

**Why a body at all.** `204 No Content` was the alternative, and it has a real argument behind it:
the entire purpose of this response is the `Set-Cookie` header, and a credential-bearing response
with an empty body is the smallest thing that can leak. It was rejected because the dashboard's very
next act is unconditionally `GET /v1/me`, so `204` buys an empty body at the cost of a second round
trip on the single flow where latency is most visible to a new user, and because the alternative is
not a *copy* of the profile shape but the same frozen shape — `AccountProfile` in
`server/app/routes/me.py` is one model, reused, so the two cannot drift. There is no caching risk,
because section 8 requires `Cache-Control: no-store` on this response regardless.

The Google subject is not in that body and never will be. It is the case the response model exists to
guard, exactly as `me.py`'s docstring says.

#### Failures

| Condition | Status | `reason` | `details` |
|---|---|---|---|
| Body is not valid JSON | `400` | `invalid_request` | `null` |
| `google_id_token` absent, empty, not a string, or an unknown field is present | `422` | `validation_failed` | `{"fields": [...]}` |
| Assertion fails issuer, audience, signature or expiry verification, or carries no `sub` claim | `401` | `unauthenticated` | `{"auth_reason": "not_linked"}` |

The `401` deserves a note, because it is the one place a reader may expect a different
discriminator. There is no principal on this route, so `credential_expired` and `wrong_client_kind`
are structurally impossible, and no grant exists to have been revoked. `not_linked` is the only
member of the closed `auth_reason` set whose meaning — "no credential was presented, or a presented
one resolves to no grant" — covers a failed sign-in attempt, and the dashboard's required behaviour
under it is exactly correct here: render signed out and offer sign-in through `POST /v1/auth/google`.
The four verification failures are **not** distinguished from one another; a client can do nothing
different with "bad audience" than with "expired", and telling an unauthenticated caller which check
failed is free reconnaissance.

### 3.2 `POST /v1/auth/pairings` — pairing creation

Extension only, unauthenticated. Nothing is bound to an account.

#### Request

| Field | Type | Required | Null allowed | Notes |
|---|---|---|---|---|
| `code_challenge` | string | yes | no | `base64url(SHA-256(verifier))`, unpadded. 43 characters from `A–Z a–z 0–9 - _` |
| `platform_token` | string | yes | no | The declared platform token. Section 5 defines the vocabulary and the mapping |

```json
{
  "code_challenge": "EXAMPLE-CHALLENGE-NOT-A-REAL-VALUE",
  "platform_token": "chrome"
}
```

`code_challenge` takes the column's own name. That is deliberate: the value is stored verbatim in
`pairing_requests.code_challenge`, and a wire name that differs from the column name for a value that
passes through unchanged is a translation layer that exists only to be gotten wrong.

**There is no `code_challenge_method` field, and sending one is a `422`.** The persistence document's
section 3.1 is explicit that `S256` is the only accepted method and that there is no method column,
"because a `plain` method is a downgrade attack and adding a second method should cost a schema
change". A wire field the server would have to validate as a constant is a field that invites a
client to send something else; its absence is the enforcement.

`code_challenge` is validated for shape at the model layer — exactly 43 characters, base64url
alphabet — and a malformed value is a `422`. That strictness is safe here in a way it explicitly is
not on the redeem route (section 4.4), because at creation there is nothing in existence yet to
disclose: a client that cannot construct a challenge has a defect, and telling it so costs nothing.

#### Response: `201 Created`

| Field | Type | Null allowed | Notes |
|---|---|---|---|
| `pairing_id` | string | no | Opaque. Appears in the approval URL |
| `user_code` | string | no | The short code in canonical form, hyphen included. Section 6 |
| `browser_label` | string | no | The mapped `browser_label` enum member the server stored. Section 5 |
| `expires_at` | timestamp | no | When the pairing dies unapproved |
| `poll_interval_seconds` | integer | no | How often the extension should poll redeem. Value from configuration (`ARCH-B4`) |

```json
{
  "pairing_id": "pair_01K5EXAMPLEPAIRINGIDAAAAAA",
  "user_code": "K7M2-9QTX",
  "browser_label": "chrome",
  "expires_at": "2026-09-14T18:27:41Z",
  "poll_interval_seconds": 3
}
```

**Why the response echoes `browser_label`.** The extension declared a platform token; the server
mapped it to a closed enum member and stored the member, not the token. Without the echo, an
extension whose token degraded to `other` has no way to know, the popup cannot display what the
dashboard will display, and the divergence is discovered by a user looking at two screens. It is one
string, server-derived, already computed. Whether the approval page *shows* a label at all is a
product question still open as `PROV-07` and this document does not answer it; making the value
available is not the same as deciding to render it.

**There is no `approval_url` field, and this was a real choice.** The extension must open a tab to
the dashboard's link page, and the server knows every environment's dashboard origin because that
origin is already in the CORS allowlist. Returning a composed URL would spare the extension a second
build-time constant. It is rejected for the reason the proposal's section 9 gives for the API base
origin: "A runtime-configurable API host is a credential-redirection bug waiting to happen." A URL
the extension will open in a tab and into which the user will then type a Google password is a
strictly worse thing to take from the network than an API host. The extension composes the approval
URL from its own pinned constant and the `pairing_id`, and a compromised or misconfigured server
cannot redirect the sign-in.

**Why `201` with no `Location` header.** A resource was created, so `201` is honest. No `Location` is
emitted because there is no route that reads a pairing — which is a gap, not a design property, and
section 10.1 states it as the one thing this document could not settle.

#### Failures

| Condition | Status | `reason` |
|---|---|---|
| Body is not valid JSON | `400` | `invalid_request` |
| Malformed `code_challenge`, absent field, unknown field | `422` | `validation_failed` |
| Creation ceiling exceeded | `429` | `rate_limited` |

### 3.3 `POST /v1/auth/pairings/{pairing_id}/approve` — pairing approval

Dashboard only, authenticated. Binds the pairing to the account signed in at that moment.

#### Request

**The body is empty.** `{}` is the canonical form; an absent body is treated as `{}`. Any field
present is a `422`.

```json
{}
```

This is the shortest section in the document and the one most likely to be got wrong, so the two
prohibitions are stated rather than implied:

- **The request must not carry an `account_id`,** and one is a `422`. The contract says the account
  "is never taken from the request"; the enforcement is that there is no field to take it from.
- **The request must not carry the `user_code`,** and one is a `422`. It is tempting to send the code
  back as proof the user compared it. The persistence document is categorical that the code is
  "never accepted as an input on any route — there is no code-entry path and there never will be";
  accepting it here, even as a redundant confirmation, creates exactly the code-entry affordance the
  anti-phishing posture is built on removing, and it makes a display string into something a server
  compares, which is the definition of a credential.

#### Response: `200 OK`

| Field | Type | Null allowed | Notes |
|---|---|---|---|
| `pairing_id` | string | no | Echoed from the path |
| `status` | string | no | Always `"approved"` on success. The `pairing_status` enum's member |
| `approved_at` | timestamp | no | The stored value, not the time of this call |

```json
{
  "pairing_id": "pair_01K5EXAMPLEPAIRINGIDAAAAAA",
  "status": "approved",
  "approved_at": "2026-09-14T18:24:03Z"
}
```

`status` carries the `pairing_status` enum member verbatim rather than a boolean or a display string,
so that the one vocabulary in the schema is the one vocabulary on the wire. On this route it can only
ever be `"approved"`; it is present anyway, because the redeem route discriminates on a field of the
same name and a client reading both should not have to learn two idioms.

`approved_at` is the **stored** timestamp. On an idempotent repeat it is the original approval time,
not the time of the repeat, which is what makes the repeat genuinely idempotent rather than merely
non-failing.

#### Failures

Approval has exactly one failure answer, for the same reason redemption does. The open-decisions
ruling in section 5.2 says: "Zero rows affected means re-read once and answer success idempotently if
the row is `approved` with the caller's own `account_id`; otherwise answer the single
indistinguishable failure."

| Condition | Status | `reason` | `details` |
|---|---|---|---|
| No dashboard principal | `401` | `unauthenticated` | per resolution order, section 5.3 of the rulings |
| Extension principal | `401` | `unauthenticated` | `{"auth_reason": "wrong_client_kind"}` |
| Unknown `pairing_id`; expired; already redeemed; bound to another account | `404` | `not_found` | `null` |
| Already approved by the calling account | `200` | — | idempotent success, original `approved_at` |
| Approval ceiling exceeded | `429` | `rate_limited` | `null` |

The `404` is the same answer, built by the same `not_found_error()` call site, as the redeem failure
in section 4. It has to be: a pairing bound to another account must be indistinguishable from one
that never existed, which is the contract's section 3.2 rule applied to a resource that happens to be
a pairing, and an authenticated attacker who could tell "approved by someone else" from "no such
pairing" would have an enumeration oracle over the pairing identifier space.

**One consequence, named rather than discovered.** The ruling's literal condition for idempotent
success is `approved` — not `redeemed`. So if the user approves, the extension redeems within a
second or two, and the user then refreshes the approval page, the re-POST answers `404`, not `200`.
That is correct: the pairing really is gone, consumed by the very redemption the approval enabled.
The dashboard must render that state as *this link request is no longer available* rather than as an
error, and must not retry. Rendering it as a failure would tell the user that a link which in fact
succeeded had failed.

### 3.4 `POST /v1/auth/pairings/{pairing_id}/redeem` — redemption

Extension only, unauthenticated. Polled on the interval the creation response supplied. Its failure
response is the subject of section 4 and is not repeated here.

#### Request

| Field | Type | Required | Null allowed | Notes |
|---|---|---|---|---|
| `code_verifier` | string | yes | no | The verifier that never left the extension until this moment |

```json
{
  "code_verifier": "EXAMPLE-VERIFIER-NOT-A-REAL-VALUE"
}
```

`code_verifier` is the symmetric partner of `code_challenge` and needs no further justification.

**The verifier is generated client-side as the unpadded base64url encoding of at least 32 bytes from
a cryptographic random source**, which yields 43 characters for 32 bytes. That is a rule on the
extension, not a validation on the server, and section 4.4 explains at length why the server must not
turn it into one.

#### Response: `200 OK`, two shapes, discriminated by `status`

Both outcomes are `200`. They are told apart by the `status` field, whose value is `"pending"` or
`"linked"`. `202 Accepted` for the pending case was considered and rejected: the contract's status
vocabulary is deliberately small, a second success status invites clients to branch on the code
rather than on the field, and both outcomes are ordinary successful reads of the same resource by the
one party entitled to read it.

**Pending result**

| Field | Type | Null allowed | Notes |
|---|---|---|---|
| `status` | string | no | `"pending"` |
| `expires_at` | timestamp | no | When to stop polling and start over |
| `poll_interval_seconds` | integer | no | Supersedes the creation value for subsequent polls |

```json
{
  "status": "pending",
  "expires_at": "2026-09-14T18:27:41Z",
  "poll_interval_seconds": 3
}
```

Repeating `poll_interval_seconds` on every pending poll is what lets the server slow a client down
without a new route or a new error, which matters on an unauthenticated, rate-limited, polled
endpoint. Repeating `expires_at` lets a service worker that was terminated and restarted mid-poll
recover its stopping condition without having persisted it.

**Linked result**

This is the credential set, and section 3.5 emits the same field names on refresh.

| Field | Type | Null allowed | Notes |
|---|---|---|---|
| `status` | string | no | `"linked"` |
| `grant_id` | string | no | The grant these credentials belong to. The extension stores it |
| `access_credential` | string | no | Opaque. Presented as `Authorization: Bearer` |
| `access_credential_expires_at` | timestamp | no | Enables proactive refresh |
| `refresh_credential` | string | no | Opaque. Presented only in the refresh request body |

```json
{
  "status": "linked",
  "grant_id": "grant_01K5EXAMPLEGRANTIDBBBBBBBB",
  "access_credential": "EXAMPLE-ACCESS-CREDENTIAL-NOT-A-REAL-VALUE",
  "access_credential_expires_at": "2026-09-14T18:39:12Z",
  "refresh_credential": "EXAMPLE-REFRESH-CREDENTIAL-NOT-A-REAL-VALUE"
}
```

Four decisions are embedded in that list and each had an alternative.

**`grant_id` is included because without it the extension cannot revoke itself.** The contract's
section 5.2 says an extension principal "may revoke only its own grant; any other grant identifier
returns `404`", which presupposes that the extension can *name* its own grant. No other route hands
it one: `GET /v1/auth/grants` is dashboard-only, and `/v1/me` carries account fields and nothing
else. This is the route that mints the grant, so this is where its identifier is disclosed. The
contract's prohibition on grant identifiers appearing in "any other route's response body" is
satisfied exactly — this is not another route.

**`access_credential_expires_at` is included; `refresh_credential_expires_at` is not.** The access
expiry lets the extension refresh just before a call rather than absorbing a guaranteed `401` on the
first call after expiry, and the contract already tells it to refresh, so handing it the timing costs
nothing. The refresh credential's own expiry was excluded because it is the wrong number to show
anyone: what actually ends a link is the grant's idle or absolute limit, not the refresh row's
`expires_at`, and publishing the latter invites both the extension and a future dashboard to present
it as "this browser stays linked until…", which would be false whenever the idle limit bites first.
Section 7.6 records the grant's limits as a deliberate exclusion with its residual named.

**No `account_id`, and no `browser_label`.** The extension can read `GET /v1/me` the moment it is
authenticated, and it already knows its label from the creation response. Putting either into a
credential-bearing body adds account data to the one response in the system that most needs to be
minimal, for no capability the extension does not already have.

**No `token_type`, and no `expires_in`.** This is not an OAuth token endpoint; there is no second
credential type to discriminate, and every other time value on this wire is an absolute RFC 3339
instant. An `expires_in` would also make the body's byte length vary with a configuration value,
which section 4.3 makes a property worth caring about on this route.

### 3.5 `POST /v1/auth/refresh` — refresh rotation

Extension only. Authenticated by the refresh credential, not by the access credential.

#### Request

| Field | Type | Required | Null allowed | Notes |
|---|---|---|---|---|
| `refresh_credential` | string | yes | no | The current refresh credential |

```json
{
  "refresh_credential": "EXAMPLE-REFRESH-CREDENTIAL-NOT-A-REAL-VALUE"
}
```

**The refresh credential travels in the body, not in `Authorization`.** The open-decisions ruling in
section 5.3 says the authentication dependency needs "two resolution modes — from `Authorization`,
and from a presented refresh credential", which reads as two presentation channels and is the
posture this freezes. The reason it is the right one is that `Authorization` on this route would make
the two credential kinds interchangeable at the point of presentation: a client bug that sent the
access credential there would be a lookup that succeeds, finds `kind = 'access'`, and must then be
refused — a refusal that has to be built and tested precisely because the channel allowed the
confusion. A named body field cannot be filled in by the generic authenticated-fetch wrapper by
accident. It also keeps the extension's single `Authorization`-setting code path honest: that wrapper
sets the access credential and nothing else, ever.

The request carries no `grant_id`. The refresh credential resolves to exactly one credential row,
which resolves to exactly one grant; a client-supplied grant identifier would be a value the server
must ignore or cross-check, and neither is better than its absence.

#### Response: `200 OK`

The credential set, with the same field names as the redeem linked result and without the `status`
discriminator, because this route has one success shape.

| Field | Type | Null allowed | Notes |
|---|---|---|---|
| `grant_id` | string | no | Unchanged by rotation. Repeated so the response is self-sufficient |
| `access_credential` | string | no | Newly minted |
| `access_credential_expires_at` | timestamp | no | |
| `refresh_credential` | string | no | The rotated-to value. The presented one is invalid immediately |

```json
{
  "grant_id": "grant_01K5EXAMPLEGRANTIDBBBBBBBB",
  "access_credential": "EXAMPLE-NEW-ACCESS-CREDENTIAL-NOT-A-REAL-VALUE",
  "access_credential_expires_at": "2026-09-14T19:11:50Z",
  "refresh_credential": "EXAMPLE-NEW-REFRESH-CREDENTIAL-NOT-A-REAL-VALUE"
}
```

`grant_id` does not change across a rotation — the persistence document is explicit that there is no
`chain_id` because "`grant_id` already is the chain identifier" — so repeating it is redundant in the
happy path. It is repeated anyway so that an extension which lost its stored grant identifier (a
cleared storage area, a partially completed install migration) recovers it on its next refresh
instead of being permanently unable to revoke itself.

#### Failures

| Condition | Status | `reason` | `details` |
|---|---|---|---|
| Presented refresh credential is rotated-away beyond the grace window, or is any older generation | `401` | `unauthenticated` | `{"auth_reason": "grant_revoked"}` |
| Presented refresh credential's grant is revoked, or past its idle or absolute limit | `401` | `unauthenticated` | `{"auth_reason": "grant_revoked"}` |
| Presented value matches nothing, or the field is absent | `401` | `unauthenticated` | `{"auth_reason": "not_linked"}` |
| Presented value is an **access** credential rather than a refresh credential | `401` | `unauthenticated` | `{"auth_reason": "not_linked"}` |
| Dashboard principal reaches this route | `401` | `unauthenticated` | `{"auth_reason": "wrong_client_kind"}` |
| Refresh ceiling exceeded | `429` | `rate_limited` | `null` |

The reuse case is the contract's own words: presenting a rotated-away refresh credential "revokes the
entire chain of credentials descended from that grant and returns `401` with `details.auth_reason` of
`grant_revoked`". Inside the grace window it rotates normally and returns `200`; the grace window's
length is configuration under `ARCH-B4`.

The access-credential-in-the-wrong-field row answers `not_linked` rather than inventing a
distinction, because from this route's standpoint the presented value is simply not a refresh
credential that resolves to a grant. The extension's `not_linked` branch — it presented something, so
this is terminal, clear everything and re-link — is the correct recovery from a client bug that has
put the wrong string in the field, and it is a loud failure rather than a quiet one.

The `wrong_client_kind` row is reachable only in the sense that a dashboard implementation could call
the route; a dashboard principal is resolved from the cookie and the route is extension-kind under
contract section 5.2. It is listed because the contract lists it.

### 3.6 `GET /v1/auth/grants` — the linked-browsers list

Dashboard only. **Extension-kind grants only** — a dashboard session is a grant and must not appear
in a list the product calls *linked browsers*. It carries no credential material of any kind.

#### Request

No body, no query parameters. Pagination is discussed below and is deliberately absent.

#### Response: `200 OK`

| Field | Type | Null allowed | Notes |
|---|---|---|---|
| `grants` | array of grant entries | no | May be empty. Never `null` |

Each entry:

| Field | Type | Null allowed | Notes |
|---|---|---|---|
| `grant_id` | string | no | The identifier `POST /v1/auth/grants/revoke` accepts |
| `browser_label` | string | no | A `browser_label` enum member. Section 5 |
| `created_at` | timestamp | no | When the browser was linked |
| `last_used_at` | timestamp | no | Coarsened; see below |

```json
{
  "grants": [
    {
      "grant_id": "grant_01K5EXAMPLEGRANTIDBBBBBBBB",
      "browser_label": "chrome",
      "created_at": "2026-09-14T18:24:07Z",
      "last_used_at": "2026-09-14T20:02:00Z"
    },
    {
      "grant_id": "grant_01K5EXAMPLEGRANTIDCCCCCCCC",
      "browser_label": "firefox",
      "created_at": "2026-08-30T09:14:55Z",
      "last_used_at": "2026-09-12T07:41:00Z"
    }
  ]
}
```

**The array is nested under a key rather than being the top-level JSON value.** Every list in this
contract is — `candidates`, `values`, `urgency_legend` — and a bare top-level array is the one shape
that cannot gain a sibling field later without breaking every client.

**`browser_label` carries the enum member, not a display string.** The contract does serve
server-rendered display text in one place: `next_action`'s canonical labels, which encode a normative
precedence and product copy that must not be re-derived per client. This is not that. A five-member
closed set naming proper nouns is trivially mapped client-side, the mapping is the only part that is
localizable, and emitting `"chrome"` keeps the wire vocabulary identical to the column vocabulary. An
implementer who wants `"Chrome"` on the screen writes it in the dashboard, once.

**`last_used_at` is coarsened, and the UI must not pretend otherwise.** The ruling in section 5.4 of
the open-decisions document requires the column to be updated only when the stored value is older
than a configured threshold, so this timestamp is accurate to within that threshold and no better.
The dashboard must render it at a granularity the coarsening supports — "2 hours ago", "yesterday" —
and must not render seconds, which would display precision the value does not have.

**Pagination is absent, and this is a judgement call with a named residual.** `PROV-06` records that
there is no cap on linked browsers, so this array is in principle unbounded; in practice it holds one
entry per browser a human uses. Adding a `page` sibling later is additive and harmless, but the
promise being made today is that **the array is complete**, and that promise is what a later
truncation would break. The alternative — shipping cursor pagination now, matching
`GET /v1/dashboard` — was rejected as surface the contract does not describe, for a list that would
paginate on its first page forever. Section 10.4 records this as an open item rather than a settled
one.

#### Failures

| Condition | Status | `reason` | `details` |
|---|---|---|---|
| No principal, or an expired, revoked or unresolvable credential | `401` | `unauthenticated` | per the resolution order |
| Extension principal | `401` | `unauthenticated` | `{"auth_reason": "wrong_client_kind"}` |

An account with no linked browsers returns `200` with `{"grants": []}`. It is not a `404`.

### 3.7 `POST /v1/auth/grants/revoke` — grant revocation

Dashboard or extension. The dashboard may revoke any grant on the account; an extension principal may
revoke only its own.

#### Request

| Field | Type | Required | Null allowed | Notes |
|---|---|---|---|---|
| `grant_id` | string | yes | no | Exactly the value `GET /v1/auth/grants` emits, or the one the redeem or refresh response gave this extension |

```json
{
  "grant_id": "grant_01K5EXAMPLEGRANTIDCCCCCCCC"
}
```

The field name is `grant_id` on the way in and `grant_id` on the way out of the list route and out of
the credential set. That is the entire point of freezing a vocabulary: a dashboard developer reading
the list response and writing the revoke request should not have to translate.

There is no `reason` field. `auth_grants.revoked_reason` is a closed, server-controlled enum whose
members describe *how the server revoked*, and the only member a route-level revoke can write is
`user_disconnected`. A client-supplied reason would be an attacker-controlled value written onto a
victim's account row, which is the same mistake the browser label exists to avoid, for a column
nobody displays.

#### Response: `204 No Content`

No body.

**Why `204` and not `200` with a `revoked_at`.** The caller has nothing to do with the timestamp; the
dashboard's next act is to re-read the list, and the extension's next act is to clear its own
storage. More usefully, an empty response makes "this grant was live and is now revoked"
indistinguishable from "this grant was already revoked", which is the right property for an
idempotent destructive operation and costs nothing to obtain.

#### Failures

| Condition | Status | `reason` | `details` |
|---|---|---|---|
| Unknown `grant_id`; a grant on another account; or, for an extension principal, any grant but its own | `404` | `not_found` | `null` |
| No principal, or an unresolvable credential | `401` | `unauthenticated` | per the resolution order |
| Absent or non-string `grant_id`, or an unknown field | `422` | `validation_failed` | `{"fields": [...]}` |

An extension revoking its own grant receives `204`, and every credential it holds is dead from that
moment; its next call returns `401` with `grant_revoked`. It must clear its credential and its local
workflow records on the `204` rather than waiting for that `401`.

**One reachability note worth stating, because it looks like a hole and is not.** The contract says
the dashboard may revoke *any* grant on the account, which includes dashboard-kind grants. But
`GET /v1/auth/grants` returns extension-kind grants only, the session cookie is opaque and carries no
readable grant identifier, and no response in this contract hands a dashboard principal a
dashboard-kind `grant_id`. So in v1 a dashboard-kind grant has no name any client can pronounce, and
self-session revocation is not reachable through this route. That is consistent rather than broken:
ending a dashboard session is sign-out, whose behaviour is decided (`MIG-19`, account-wide) and whose
route is deferred. If the sign-out route is later built on top of this one, it will need a way to
name the session's own grant, and that is a change to the sign-out design rather than to this one.

---

## 4. The redeem route's failure response

This is the most consequential decision in the document, so it is made in its own section with its
reasoning in full.

### 4.1 What the accepted documents require, and what they leave open

Two normative sources say the same thing and neither finishes the sentence.

The persistence proposal, section 10: "Unknown pairing, expired pairing, already-redeemed pairing,
and wrong verifier are **indistinguishable** — same status, same reason, same message, no
timing-observable branch before the verifier comparison. Distinguishing them would turn the redeem
route into an oracle for whether a pairing identifier exists and whether it has been approved. The
contract does not specify these responses at all; section 11 records that as a gap."

The open-decisions ruling, section 5.3: "The pairing routes collapse every failure into one answer.
Unknown pairing, expired pairing, already-redeemed pairing and wrong verifier are indistinguishable —
same status, same reason, same message, and no timing-observable branch before the verifier
comparison."

Both say the four cases are indistinguishable *from one another*. Neither says what they are
indistinguishable *as*. Four implementers will pick four answers, and the wrong answer here does not
produce a cosmetic inconsistency — it produces the approval oracle that the verifier-before-status
check ordering exists to prevent, or it sends the extension down a terminal cleanup branch on an
ordinary poll.

### 4.2 The decision

> **The single indistinguishable failure of `POST /v1/auth/pairings/{pairing_id}/redeem` is
> `404 not_found`, with the contract's standard message, and `details` present and `null`.**
>
> **No `auth_reason` is carried, and no new `auth_reason` member is needed.**

```json
{
  "reason": "not_found",
  "message": "The requested resource was not found.",
  "request_id": "req_0123456789abcdef0123456789abcdef",
  "details": null
}
```

The same answer serves the approve route's single failure (section 3.3) and the revoke route's
unknown-grant case (section 3.7), and all three are produced by the one `not_found_error()`
constructor in `server/app/api/errors.py`, whose docstring already states the property this decision
depends on: it is "the single call site for both 'no such resource' and 'that resource belongs to
another account' — the contract requires the two to be indistinguishable on the wire, and routing
both cases through one function is what makes that true by construction rather than by convention."
Adding a third and fourth case to that call site is using the mechanism for exactly what it is.

### 4.3 Why `404`, and what was rejected

**`401 unauthenticated` with an `auth_reason` was the obvious candidate and it is wrong.** The redeem
route is unauthenticated: it carries no principal, resolves no credential, and touches no grant. Every
member of the closed `auth_reason` set is defined in terms of something this route does not have.
`credential_expired` describes an access credential past its lifetime against a live grant — there is
neither. `grant_revoked` describes a grant that is gone — no grant exists until this call succeeds.
`wrong_client_kind` describes a valid principal of the wrong kind — there is no principal.
`account_deleted` is reserved and unreachable in v1 by the ruling. That leaves `not_linked`, which
*sounds* apt and is the most dangerous option on the list, because it is the one that would be
chosen by an implementer reasoning from the name. `not_linked` has a required client behaviour
attached to it in contract section 4.1: an extension that presented a credential must treat it as
**terminal** and clear the credential, the local workflow records *and the checkpoints*. An extension
polling the redeem route holds no credential yet, so it would take the other branch — offer the
linking flow, clear nothing — which happens to be survivable. But it would be survivable by accident,
on a route polled several times a second, with a discriminator whose documented meaning is "this
browser's link is gone" being returned to a browser that is in the middle of establishing one. A
discriminator that means the opposite of the situation it describes is a defect waiting for the first
implementer who reads the table instead of this paragraph.

**A new `auth_reason` member was considered and is not needed.** The set is closed and adding a value
is a breaking change, so the bar is that no existing answer fits. An existing answer fits, and it
fits better than a new member would: the failure is about a *resource named in the path*, not about a
principal, and `auth_reason` is the discriminator for `401`s about principals. Minting, say,
`pairing_unavailable` would put a value into a `401`-scoped enum for a response that is not a `401`,
and would oblige both clients to learn a value whose only correct handling is "stop polling" —
which is what a `404` on a polled resource already means.

**`409 state_transition_not_allowed` or `409 state_blocked`.** Both are about return-state
transitions and both are structurally incapable of covering the set: a `409` asserts that a resource
exists and is in the wrong state, which is true for the consumed and expired cases and a lie for the
unknown-pairing case. The lie is the leak — answering `409` for three cases and something else for
the fourth is the oracle.

**`422 validation_failed`.** Wrong twice over. It asserts that a field is invalid, which is false for
three of the four cases, and it carries a `details.fields` array whose contents and length would vary
with what the handler found — which section 4.4 makes a property this route cannot afford.

**`400 invalid_request`.** `server/app/api/errors.py` maps this to malformed JSON and request syntax,
and a genuinely malformed body must keep returning it. Overloading it would mean a client cannot tell
a broken request from a dead pairing — tolerable — but it would also mean the four cases and the
malformed-body case share an answer, which makes the malformed-body case indistinguishable too, and
that is a diagnostic loss with no security gain.

**Why `404` is true rather than merely convenient.** This is the part worth being precise about,
because a status code chosen for its opacity rather than its meaning tends to get "corrected" later.
The persistence document says of the pairing identifier: it "is an addressing value that appears in a
URL; it is not a credential and confers nothing on its own, **because redemption requires the
verifier**." Take that seriously and the redeemable resource is not named by `pairing_id` alone — it
is named by the pair `(pairing_id, code_verifier)`. The verifier is part of the name. Under that
reading all four cases are the same case: *there is no redeemable pairing at the name you gave*. An
unknown identifier names nothing. An expired or consumed pairing names nothing redeemable. A wrong
verifier is a wrong name. `404 not_found` — "Resource absent or outside the account scope" — is the
literal truth in all four, and it is the same reasoning by which the contract's section 3.2 returns
`404` rather than `403` for another account's item: the API does not reveal existence to a caller who
cannot demonstrate entitlement.

### 4.4 Making it actually indistinguishable

Choosing one status is the easy half. The response must also not be distinguishable by which fields
are present, by body length, or by timing.

**By fields present.** The envelope is `reason`, `message`, `request_id`, `details`, and
`server/app/api/errors.py` serializes all four keys on every error. `details` must be **present and
`null`**, not omitted and not `{}`. `not_found_error()` takes no `details` argument, so this holds by
construction as long as the four cases go through it. No `auth_reason`, no `retry_after`, no
`pairing_status`, no field that exists in one case and not another.

**By body length.** `reason` and `message` are fixed strings from a single constructor. `details` is
the four bytes `null`. `request_id` is produced by `_new_request_id()` as `req_` plus a 32-character
lowercase hex UUID — **a fixed 36 characters, always**. The four failure bodies are therefore
byte-length-identical, not merely similar, and that is assertable in a test rather than reviewable by
eye. This is a real constraint on future edits: a `message` that interpolated anything, or a
`request_id` of variable length, would silently reintroduce a length channel.

**By headers.** All four carry the identical header set from section 8 — same `Cache-Control`, same
`Vary: Origin`, same CORS headers for the extension origin, no `Retry-After` on some and not others,
no `WWW-Authenticate` at all.

**By timing.** Four rules, then an honest statement of the residual.

1. **Check the verifier before the status, on every poll**, as both normative documents require. The
   cleanest way to satisfy this is to fold the challenge into the consuming statement's predicate, so
   that the four cases are not four branches but one statement:

   ```sql
   UPDATE pairing_requests
      SET status = 'redeemed',
          redeemed_at = :now
    WHERE id = :pairing_id
      AND code_challenge = :presented_challenge
      AND status = 'approved'
      AND expires_at > :now
   RETURNING account_id, browser_label;
   ```

   Zero rows affected is the single failure, whichever conjunct failed. There is no application-level
   branch to time, because there is no application-level branch. The ruling's "check the verifier
   before status" is satisfied a fortiori when nothing is checked separately at all.
2. **If the comparison is ever done in Python instead** — for instance because a future
   implementation reads the row first — it must use a constant-time comparison, and it must perform
   the same comparison against a fixed decoy value of the same length when no row was found, so that
   the unknown-identifier case does the same work as the wrong-verifier case.
3. **The serialization-failure branch produces the same response.** Under `REPEATABLE READ` or
   `SERIALIZABLE` the losing concurrent redemption raises `40001`; that is "lost the race", it returns
   the same `404`, and it is **never blindly retried**, because a blind retry of a consumed pairing is
   the double-issue the predicate exists to prevent.
4. **Logging must not branch either.** One log event for the outcome, with no field distinguishing
   which conjunct failed, and — per section 2 — no pairing identifier, verifier or challenge in it.
   A per-case log line is both a timing difference and a disclosure to anyone reading logs.

**The residual, stated rather than claimed away.** Perfect timing equality against a database is not
achievable. An unknown identifier misses the primary-key index; a known one hits it, takes a row
lock, and may block behind a concurrent redemption. That difference is sub-millisecond, it is
measured across internet latency and a rate-limited endpoint, and it is dwarfed by ordinary variance.
What this document freezes is the achievable claim: **no branch in application code, no field, no
header and no byte of the response body varies across the four cases.** The remaining channel is the
storage engine's, it is not removable without a fixed-time sleep whose length would itself be a
configuration number this ticket may not invent, and it is recorded here so that a future reviewer
finds it named rather than discovers it as an omission.

### 4.5 One thing that stays distinguishable, on purpose

`429 rate_limited` remains a distinct answer on this route. It is not part of the indistinguishable
set and must not be folded into it: the contract enumerates it for the pairing routes explicitly, a
client must be able to back off rather than hammer, and the information it discloses — "you are
polling too fast" — is about the caller, not about the pairing. The `404` and the `429` are the only
two failure answers this route ever produces.

### 4.6 What the extension does with it

Stop polling this pairing. Do not retry, do not treat it as an authentication failure, do not clear
anything (there is nothing to clear — the extension holds no credential at this point in the flow),
and offer to start a new link. A `404` mid-poll most often means the pairing expired while the user
was doing something else, and the truthful copy is *this link request expired — try again*.

---

## 5. The browser-label vocabulary

### 5.1 The problem this closes

`browser_label` is a **native PostgreSQL enum** with five members — `chrome`, `firefox`, `edge`,
`safari`, `other` — on both `pairing_requests` and `auth_grants`. The persistence document decided it
must be "a closed server-side vocabulary, mapped from a small declared platform token, bounded, never
the raw user-agent string, never free text", because in the phishing scenario the label exists to
defend against, the attacker is the party supplying it. The open-decisions ruling repeats that
verbatim. **Neither document defines the token set or the mapping**, so the field that carries the
token has no vocabulary and the mapping has no table.

There is no migration tooling in this repository. Adding an enum member is a schema change with no
mechanism to apply it. So the mapping must be **total** over every value a client could ever send,
and every value it cannot place must degrade to an existing member.

### 5.2 The token set

`platform_token` on `POST /v1/auth/pairings` is an **open vocabulary with a closed recognized set**,
not a closed enum. The distinction matters and is an explicit, reasoned exception to the contract's
section 3.1 rule that unknown enum values fail the request.

The reason is deployment asymmetry. The extension auto-updates in the user's browser; the server
deploys separately and may lag by days. If `platform_token` were a closed request enum, a newer
extension declaring a token an older server has never heard of would receive `422` on
`POST /v1/auth/pairings` — and that route is the **first step of linking**, so the failure mode is an
install that cannot link at all until the server catches up. A degradation to `other` costs a less
precise label in the linked-browsers list. A `422` costs the product.

The syntactic rule is still enforced, because a malformed value is contract drift rather than a newer
client:

- `platform_token` is a string of **1 to 32 characters** drawn from lowercase ASCII letters, digits
  and the hyphen. Anything else — a non-string, an over-long value, uppercase, whitespace, punctuation
  — is `422 validation_failed`.

The tokens an extension may declare:

| Token | Meaning | Extension must send it when |
|---|---|---|
| `chrome` | Google Chrome | It is running in Chrome |
| `firefox` | Mozilla Firefox | It is running in Firefox |
| `edge` | Microsoft Edge | It is running in Edge |
| `safari` | Apple Safari | It is running in Safari |
| `chromium` | Chromium itself | It is running in an unbranded Chromium build |
| `brave` | Brave | It is running in Brave |
| `opera` | Opera | It is running in Opera |
| `vivaldi` | Vivaldi | It is running in Vivaldi |
| `arc` | Arc | It is running in Arc |
| `other` | Deliberately unidentified | It cannot determine the browser, or declines to |

The extension determines the token locally — from `navigator.userAgentData.brands` where available,
from its own build target otherwise — and **the evidence never leaves the browser**. The raw
user-agent string is never sent, and the token itself is never stored or logged by the server: it is
read, mapped, and discarded, so nothing attacker-chosen survives the request.

### 5.3 The mapping, which is total

| `platform_token` | Stored `browser_label` |
|---|---|
| `chrome` | `chrome` |
| `firefox` | `firefox` |
| `edge` | `edge` |
| `safari` | `safari` |
| `chromium` | `other` |
| `brave` | `other` |
| `opera` | `other` |
| `vivaldi` | `other` |
| `arc` | `other` |
| `other` | `other` |
| **any other syntactically valid string** | `other` |

**Why the Chromium derivatives map to `other` rather than to `chrome`.** They are Chromium-based, and
an implementer will be tempted to fold them in so the list says something useful. It is the wrong
call for a security surface. This label's job is to help a user recognise which browser a grant
belongs to and to spot an approval they did not initiate. Showing "Chrome" to a Brave user is
confidently wrong: the user looks at the linked-browsers list, sees a Chrome they do not use, and
either dismisses a real browser of theirs as suspicious or learns to ignore the field. Showing "Other
browser" is vague and true. **On a list whose purpose is recognition, truthful-and-vague beats
confidently-wrong**, and it is the only one of the two that fails in a direction the user can reason
about.

**Why the derivative tokens are named at all, if they all land on `other`.** Their behaviour today is
identical to an unrecognised string, so the rows are documentary rather than operational — and that
is worth the four lines. They record that the degradation is a decision rather than an oversight,
they tell an extension author which spelling to use, and when migration tooling exists, promoting one
to its own enum member is a one-row edit in this table plus a migration, in the single place the
mapping lives, rather than a re-derivation from first principles by whoever notices first.

### 5.4 Where the label is set, and where it is copied

The label is computed **once**, at `POST /v1/auth/pairings`, from the declared token, and written to
`pairing_requests.browser_label`. At redemption it is copied to `auth_grants.browser_label` from the
consuming statement's `RETURNING` clause — which is exactly why that clause returns
`account_id, browser_label` and nothing else.

**The redeem request carries no `platform_token`, and must not.** Accepting one would let a caller
declare a different browser at redemption than at creation, which would mean the label shown on the
approval page is not the label stored on the grant — turning a field whose entire purpose is helping
a user recognise an approval into a field that can lie about what was approved.

---

## 6. The short code

### 6.1 Why this is not a display concern

The persistence document proposes "eight characters from a 32-symbol alphabet with the ambiguous
glyphs removed, grouped `XXXX-XXXX`", and then says "the alphabet and grouping are display concerns;
the persistence requirement is only that the column stores exactly what is shown."

That is right about the column and wrong about the concern. The code's single job is that a human
compares it across two surfaces — the extension popup and the dashboard approval page — and confirms
they match. Two surfaces that agree on the value but disagree on its *presentation* produce a
mismatch the user is being trained to treat as an attack. If one renders `K7M29QTX` and the other
`K7M2-9QTX`, or one uppercases and the other does not, the comparison fails on a difference that is
purely cosmetic and the user does the right thing for the wrong reason — or, worse, learns that
mismatches are normal. The presentation is therefore part of the security control, and it is frozen
here.

### 6.2 The alphabet

**Crockford Base32**, thirty-two symbols, in this order:

```
0 1 2 3 4 5 6 7 8 9 A B C D E F G H J K M N P Q R S T V W X Y Z
```

Excluded: **`I`, `L`, `O`, `U`**. The first three are excluded because they are the confusable ones —
`I` against `1`, `L` against `1`, `O` against `0` — and removing the letters rather than the digits
keeps the full digit range, which matters for a code users may read aloud over a phone even though no
route accepts one typed back. `U` is excluded to reduce the chance of an offensive string appearing
in a code shown on a stranger's screen.

Rejected: **RFC 4648 Base32** (`A`–`Z`, `2`–`7`), which is also 32 symbols and also visually safe,
because it removes the ambiguity by removing the digits `0` and `1` entirely rather than by removing
the letters — leaving a code with no `0`, `1`, `8` or `9`, which reads as arbitrary rather than as a
deliberate exclusion, and retaining `I`, `L` and `O`, whose absence is the property a user comparing
two screens actually benefits from. Rejected: a bespoke alphabet, because Crockford is published and
stable, and two independently written implementations that both say "Crockford Base32" agree by
construction, which is the whole point.

Rejected as **out of scope**: an offensive-string deny-list. Excluding `U` reduces the risk and does
not eliminate it; `A` and `E` remain, and a deny-list is a product and localisation decision, not a
wire format. Section 10.5 records it.

### 6.3 Length, grouping, casing and the stored value

- **Eight characters** drawn uniformly at random from the alphabet above, using a cryptographic
  random source. Forty bits.
- **Grouped `XXXX-XXXX`** with a single ASCII hyphen-minus, `U+002D`. Never an en dash, never a
  non-breaking hyphen, never a space.
- **Canonical casing is uppercase.**
- **The canonical value is the nine-character string including the hyphen**, and that is what is
  stored in `pairing_requests.user_code` and what appears in the `user_code` field of the creation
  response.

That last point is the one that closes the divergence. The persistence document requires the column to
store "exactly what is shown"; this makes the hyphen part of what is shown and therefore part of what
is stored, rather than a separator each surface inserts at render time. Two surfaces that both receive
`"K7M2-9QTX"` and both print it verbatim cannot disagree. Two surfaces that receive `"K7M29QTX"` and
each insert a separator can, and one of them will eventually be a dashboard build that renders it as
`K7M2 9QTX` because a designer preferred a space. The partial unique index over pending rows operates
on the stored nine-character value, which is correct and needs no change.

### 6.4 Rendering rules, binding on both surfaces

Both the extension popup and the dashboard approval page must:

- render the `user_code` string **verbatim**, character for character;
- not re-case it, and specifically not use CSS `text-transform` to fake either case — the value
  arrives uppercase and is displayed uppercase;
- not re-group it, insert spaces, or strip or substitute the hyphen;
- render it in a face where the surviving glyphs are distinguishable — a monospace or tabular face,
  ideally one with a slashed or dotted zero, since `0` and the letter `O`'s absence is a property the
  user cannot see and should not have to rely on;
- not truncate, wrap mid-code, or allow a line break inside it.

### 6.5 Case-insensitive comparison: the direct answer

**There is no comparison to make case-insensitive, and that is the answer rather than a dodge.**

The code is displayed and never submitted. There is no lookup index on it, no code-entry route, and —
per the ruling in section 5.2 of the open-decisions document — there never will be one. The server
never receives a code and therefore never compares one. The only comparison in the system is the
human's, between two surfaces that both render the identical string the server produced, so the rule
that matters is byte-identical rendering (section 6.4), not a normalisation function.

This document therefore **deliberately specifies no normalisation function**. Specifying one — "strip
hyphens, uppercase, then compare" — would imply an input path that does not exist, and a helper
function named `normalize_user_code` sitting in the codebase is an invitation to build the route that
would use it. If a code-entry route is ever wanted, it is a new decision that must reopen the
anti-phishing posture the ruling built on its absence, and the normalisation rule is written then, as
part of that decision.

For the record, so that the future decision does not have to re-derive it: were such a route ever
added, comparison would have to be case-insensitive and hyphen-insensitive, because a user typing a
displayed code will lowercase it and will omit or add the separator. That is a note, not a
specification, and nothing in v1 implements it.

---

## 7. Fields and values deliberately absent

Collected so that an implementer who notices one missing finds the reason rather than adding it.

1. **`code_challenge_method`** — section 3.2. `S256` only; a method field is a downgrade affordance.
2. **`approval_url`** — section 3.2. The extension composes it from a pinned constant.
3. **`account_id` on any of the seven** — the contract forbids a client choosing the account, and
   `GET /v1/me` serves it to a principal that already has one.
4. **`token_type` and `expires_in`** — section 3.4. Not an OAuth endpoint; absolute instants
   throughout.
5. **`refresh_credential_expires_at`** — section 3.4. It is not the link's lifetime and would be
   presented as though it were.
6. **The grant's `idle_expires_at` and `absolute_expires_at`** — not emitted on the credential set or
   on the grants list. They are the values that actually end a link, and showing them would be
   genuinely useful to a user ("this browser will need re-linking on…"). They are excluded because
   both are configuration-derived under `ARCH-B4` with no values chosen, because the idle limit is
   evaluated against a **coarsened** `last_used_at` and so the displayed date would be wrong by up to
   the coarsening interval in a direction the user cannot see, and because presenting an idle deadline
   that silently moves every time the extension is used is a worse user experience than presenting
   nothing. **This is a real omission with a real cost**, and section 10.6 records it as a decision
   that should be revisited once the numbers exist.
7. **A `reason` field on the revoke request** — section 3.7. Attacker-controlled text on a victim's
   row.
8. **`WWW-Authenticate` on any `401`** — section 8. A browser presented with a `Basic` or `Bearer`
   challenge may surface a native credential prompt, which is wrong on the dashboard leg and
   meaningless on the extension leg. The contract defines no challenge and none is emitted.

---

## 8. Headers, per route

Two rules come straight from the contract and are restated because every row below depends on them.
`Vary: Origin` is sent on **every** response — success, error, and preflight — so that an allowlist
decision is never cached across origins (section 3.5). Responses carrying a credential use
`Cache-Control: no-store` (section 3.4). `X-Request-ID` is emitted on every response by the
request-id middleware in `server/app/api/errors.py` and is not repeated in the table.

### 8.1 `Cache-Control` on all seven

**Every response from every one of these seven routes carries `Cache-Control: no-store`**, on success
and on failure alike.

The contract's section 3.4 names only "the redemption and refresh responses" as credential-bearing,
and that enumeration is under-inclusive: `POST /v1/auth/google` delivers a session credential in a
`Set-Cookie` header, `POST /v1/auth/pairings` returns the short code and the pairing identifier, and
`GET /v1/auth/grants` returns the identifiers that the revoke route accepts. There is no response on
any of these seven routes that is safe for a shared cache to store. A per-route rule is a rule someone
will eventually get wrong on the one route where it matters, so the rule is uniform.

The bare `no-store` form is used, not the `private, no-store` form the contract applies to order and
return responses. `private` constrains shared caches; `no-store` already forbids storage by any cache,
shared or not, so the pair adds nothing, and mixing the two spellings across routes invites the
question of whether the difference is meaningful. It is not.

### 8.2 Per-route table

| Route | Origin allowed | `Access-Control-Allow-Credentials` | `Cache-Control` | `Set-Cookie` | Strict `Origin` match required |
|---|---|---|---|---|---|
| `POST /v1/auth/google` | Dashboard origin | `true` | `no-store` | **Yes** — sets the session cookie | Yes (mutating dashboard route) |
| `POST /v1/auth/pairings` | Extension origin | **Never sent** | `no-store` | No | No — no ambient credential exists |
| `POST /v1/auth/pairings/{id}/approve` | Dashboard origin | `true` | `no-store` | No | **Yes** |
| `POST /v1/auth/pairings/{id}/redeem` | Extension origin | **Never sent** | `no-store` | No | No |
| `POST /v1/auth/refresh` | Extension origin | **Never sent** | `no-store` | No | No |
| `GET /v1/auth/grants` | Dashboard origin | `true` | `no-store` | No | No — non-mutating |
| `POST /v1/auth/grants/revoke` | Dashboard **or** extension origin | `true` for the dashboard origin only | `no-store` | No | **Yes for a dashboard principal**; not applicable to an extension principal |

`Vary: Origin` on every row, without exception, including every `404`, every `401`, every `422`,
every `429` and every preflight. The redeem route's `404` carries it too, which is not a formality:
without it a cache keyed on the URL alone could serve one origin's response to another, and the one
response in this system whose uniformity is load-bearing is that `404`.

The revoke row is the only one with a conditional, and it follows directly from section 3.5 of the
contract: credentials cross only on the dashboard origin, so `Access-Control-Allow-Credentials` is
never emitted for the extension origin even on a route both may call, and the `Origin`-matching
requirement attaches to the ambient-credential leg because that is the leg it defends.

### 8.3 Preflight

The extension leg is preflighted because `Authorization` is not a safelisted request header.
Preflight responses on all seven routes allow `authorization` and `content-type`, echo the exact
requesting origin when it is on the allowlist, carry `Vary: Origin`, and carry an
`Access-Control-Max-Age` whose value is environment configuration. **No wildcard origin is emitted,
in any environment, on any route, for any client**, and an origin absent from the allowlist is
refused rather than answered with a permissive header or silently allowed by omitting the CORS
headers.

`authorization` is allowed uniformly, including on the three unauthenticated routes, which never read
it. A per-route allow-list of headers would be a second place for the allowlist to drift.

### 8.4 The session cookie

The contract fixes the cookie's attributes — `Secure`, `HttpOnly`, `SameSite=Lax` — and names neither
the cookie nor its `Path` or `Domain`. Two implementers will pick two names, so:

> **The dashboard session cookie is `__Host-boomerang_session`.**
>
> `Set-Cookie: __Host-boomerang_session=<opaque>; Secure; HttpOnly; SameSite=Lax; Path=/`
>
> **No `Domain` attribute**, ever.

The `__Host-` prefix is browser-enforced and requires exactly the three properties this design already
wants: `Secure`, `Path=/`, and **no `Domain` attribute**. The no-`Domain` part is the one worth
having. The cookie is set by the API on its own response, so it defaults to the API host and is
returned to the API host, which is all that is required — the dashboard never reads it, because it is
`HttpOnly`. `SameSite=Lax` still permits the dashboard's cross-origin POSTs because same-site is
determined by registrable domain, and the two origins share one by the precondition the open-decisions
document records. So no `Domain` attribute is needed, and `__Host-` makes that structural: a sibling
host under the shared registrable domain cannot set a cookie of this name for the API host. That is
precisely the attack the contract's section 3.5 names when explaining why double-submit was rejected —
"an attacker who can write a cookie on the registrable domain" — so taking the free structural
defence against it is consistent rather than incidental.

`__Host-` works in development: `Secure` cookies are accepted on `http://localhost` by current
browsers, cookies ignore ports, and `Path=/` and the absent `Domain` are unaffected.

The cookie's value is an opaque access credential, stored as an `auth_credentials` row with
`kind = 'access'` pointing at a grant with `client_kind = 'dashboard'` — there is no separate session
store, exactly as the shipped schema's docstring says. Nothing about the cookie's value is parseable
by the client and no client ever tries.

On a `401` carrying `details.auth_reason` of `grant_revoked` to a dashboard principal, the server
clears the cookie on that same response, because contract section 4.1 says it must: "The dashboard
cannot clear its own cookie, which is `HttpOnly`; the server clears it on the response that carries
this discriminator." The clearing `Set-Cookie` must repeat the identical name, `Path` and attributes,
or the browser will not match it.

---

## 9. Implementation notes that follow from the shapes

Not a design section; four consequences an implementer will otherwise hit.

**One response model per shape, in the style of `server/app/routes/me.py`.** Never an ORM row. The
model is what keeps `google_subject`, `credential_hash`, `code_challenge` and `generation` off the
wire — not a reviewer's memory. A column added to storage must not become a response field by
accident, and on these tables that accident is a credential disclosure rather than a cosmetic leak.

**The credential set is one model, used in two places.** `grant_id`, `access_credential`,
`access_credential_expires_at`, `refresh_credential`. The redeem linked result adds `status`; the
refresh response is the set alone. Defining it twice is how the two drift.

**Errors are raised, never constructed.** Route code raises `ApiError` or a convenience constructor;
`install_error_handling` is the only thing that builds a wire-level error response. The four redeem
failures raise `not_found_error()` — the same call, with no arguments, from one place in the handler.
A handler with four `raise` statements is a handler whose four messages can diverge.

**Tests these shapes imply**, beyond the lists already in the contract's section 14 and the
open-decisions document's section 5.9:

1. the four redeem failures produce byte-identical response bodies except for `request_id`, and
   identical `Cache-Control` and `Vary` headers;
2. the redeem failure body's `details` key is present and `null`, and no `auth_reason` appears
   anywhere in it;
3. a redeem call with a syntactically valid but wrong verifier against a `pending` pairing and one
   against an `approved` pairing are indistinguishable in status, body and headers;
4. `POST /v1/auth/pairings` with an unrecognised `platform_token` returns `201` and stores
   `browser_label = 'other'`, and with a malformed one returns `422`;
5. the `user_code` returned by pairing creation is exactly the value stored in
   `pairing_requests.user_code`, hyphen included, and contains no character outside the frozen
   alphabet;
6. `GET /v1/auth/grants` emits `browser_label` as an enum member string and never a display string,
   and never a dashboard-kind grant;
7. every response from all seven routes carries `Vary: Origin` and `Cache-Control: no-store`,
   including `429` and `404`;
8. `POST /v1/auth/google` sets `__Host-boomerang_session` with no `Domain` attribute, and a `401`
   carrying `grant_revoked` to a dashboard principal clears it with matching attributes;
9. every request model rejects an unknown field with `422`, and specifically: `account_id` or
   `user_code` on approve, `platform_token` on redeem, `code_challenge_method` on pairing creation.

---

## 10. What this document could not settle

Marked explicitly rather than quietly decided. Each is a question for the contract owner or the user,
stated as a question.

### 10.1 The approval page has no route to read the pairing

**This is the most serious gap and it blocks the dashboard's link page.**

The proposal's section 6 step 3 requires: "The link page shows what is being approved and the same
short code the popup is displaying." The frozen route set contains seven routes, and **none of them
reads a pairing.** There is no `GET /v1/auth/pairings/{pairing_id}`. The approval page receives the
`pairing_id` in its URL and has no way to obtain the `user_code` it must display before the user
approves — the approve route returns the code only after the act it was supposed to inform.

Two workarounds exist and one of them is a security regression:

- **Carry the code in the approval URL** alongside the identifier. This needs no new route, and it is
  wrong. The attacker in the device-code phishing scenario composes that URL. They can put the
  victim's *own* popup code in it — read from a screenshot, or shoulder-surfed — while the
  `pairing_id` names the attacker's pairing. The page then displays a code that matches the victim's
  popup and approves a pairing that does not. The comparison step, which is the flow's primary
  human-facing defence, is defeated by construction. A server-authoritative read does not have this
  property, because the code the page renders is the one bound to the pairing being approved.
- **Add an eighth route.** `GET /v1/auth/pairings/{pairing_id}`, dashboard-only, authenticated,
  returning `pairing_id`, `user_code`, `browser_label` and `expires_at` and nothing else. The
  disclosure is modest — the code confers nothing, is never submitted, and is already known to
  whoever started the pairing — and a pairing that is unknown, expired or consumed returns the same
  `404 not_found` as every other pairing failure.

> **Question for the contract owner: may an eighth authentication route,
> `GET /v1/auth/pairings/{pairing_id}` (dashboard only, authenticated), be added to contract section
> 5? Without it the approval page cannot display a trustworthy short code, and the only alternative
> defeats the code comparison in exactly the scenario it exists to defend.**

This document does not add it, because the contract freezes "the existence, path, method and required
caller of every authentication route in section 5" and adding one is a coordinated change, not a
field-naming change.

### 10.2 What the approval page displays

`PROV-07` records "what the approval screen shows" as open, and the proposal's section 13 item 5 asks
whether the screen should show anything identifying the browser being linked — a label, an
approximate location, a time — noting that each helps a user spot a phishing attempt and each is a
new piece of data being stored. This document makes `browser_label` **available** on the wire. It does
not decide whether the approval page renders it. If the answer is that it should, section 10.1's route
is the thing that delivers it, and the two questions should be answered together.

### 10.3 Whether the pairing creation response should carry the grant's future limits

Not answerable before `ARCH-B4` sets the numbers. See section 7 item 6.

### 10.4 `GET /v1/auth/grants` pagination

Frozen unpaginated, with the promise that the array is complete. `PROV-06` records that there is no
cap on linked browsers. If a cap is introduced, or if the list is ever paginated, the completeness
promise breaks and that is a contract change. Flagged so it is decided rather than discovered.

### 10.5 An offensive-string deny-list for generated short codes

Excluding `U` from the alphabet reduces the chance and does not eliminate it. Whether generated codes
are screened against a deny-list, and in which languages, is a product and localisation decision. No
screening is specified here; the regenerate-on-conflict retry at creation is the obvious place to
attach one if it is wanted.

### 10.6 The grants list's `last_used_at` precision

The value is coarsened by a configured interval that does not yet exist. The rendering rule in
section 3.6 — never show seconds — is derived from the coarsening rather than from a known number, and
should be revisited when the number is chosen.

---

## 11. Amendments other documents need

This document creates no obligation to edit anything, and does not edit anything. Each item below is
named precisely so it can be dispatched as its own change.

| Document | Location | Edit |
|---|---|---|
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §2, the "intentionally not frozen" list | The first bullet — "request and response field names for the authentication routes in section 5.1" — is the entry this document closes. Replace it with a reference to this document, or the contract continues to say the names are unfrozen after they have been frozen |
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §5.1, the paragraph beginning "Request and response **field names for these seven routes are not yet frozen**" | Same correction, in the place an implementer actually reads |
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §3.4, "Responses that carry a credential — the redemption and refresh responses in section 5.1" | **Under-inclusive as written.** `POST /v1/auth/google` delivers a session credential in `Set-Cookie`, and `POST /v1/auth/pairings` and `GET /v1/auth/grants` return values that must not be cached. Widen it to all seven authentication routes, per section 8.1 here |
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §5.1, the redeem paragraph | It describes the pending and success results and is silent on the failure. Add the `404 not_found` ruling from section 4 here, or the gap the persistence document's §11 recorded stays open in the contract itself |
| [`boomerang-api-contract.md`](boomerang-api-contract.md) | §14, contract tests | Add the nine assertions in section 9 here |
| [`boomerang-pairing-persistence.md`](boomerang-pairing-persistence.md) | §4.3, "The alphabet and grouping are display concerns" | **Wrong as written**, for the reason in section 6.1 here: the comparison across two surfaces is the control, so its presentation is part of it. Replace with a reference to section 6 here |
| [`boomerang-pairing-persistence.md`](boomerang-pairing-persistence.md) | §11, the list of gaps | Gap on the unspecified redeem failure responses is closed by section 4 here and can be marked so |

Two of those — the §2 and §5.1 "not frozen" statements — matter more than the rest, because an
implementer who reads only the contract will believe they are free to invent names, which is the
situation this document was written to end.

---

## 12. Where these decisions are registered

These belong in [`../plan/boomerang-decisions.md`](../plan/boomerang-decisions.md) alongside the
authentication decisions already recorded there as `MIG-17`, `MIG-18`, `MIG-19`, `PROV-05` through
`PROV-08`:

- the seven routes' frozen request and response field names;
- the redeem route's single indistinguishable failure being `404 not_found` with no `auth_reason`,
  and the finding that **no new `auth_reason` member is required**;
- the `platform_token` vocabulary and its total mapping to `browser_label`, including the open-
  vocabulary exception to the contract's closed-enum rule and the reason for it;
- Crockford Base32, eight characters, `XXXX-XXXX`, uppercase, hyphen stored;
- `__Host-boomerang_session` with no `Domain` attribute; and
- `Cache-Control: no-store` on all seven authentication routes rather than on two.

The unresolved items in section 10 are not decisions and are not registered as such. Section 10.1 —
the missing read route for the approval page — should be raised as its own contract question rather
than carried as a design open, because it blocks a screen that the accepted mechanism requires and
has no acceptable workaround.
