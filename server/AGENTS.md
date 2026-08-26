# server/AGENTS.md

FastAPI service. Read [`../AGENTS.md`](../AGENTS.md) first for repo-wide rules.

## Scope

The server is a **stateless broker and inference host**. It:

- turns messy order-page DOM into structured orders, via Bedrock
- ranks orders by return-window urgency
- brokers USPS eligibility and pickup scheduling
- holds every credential in the system

It does **not** own a browser, touch a retailer session, or hold a user credential.

**Stateless means stateless.** The server persists nothing between requests — no orders, no
addresses, no pickup records, no database, no cache. Every request carries what it needs. If you
find yourself wanting somewhere to put something between two calls, put it in the response and let
the extension hold it.

**The server never initiates anything.** Every code path starts with a request from the extension
or the dashboard. There is no poller, no scheduler, no webhook to a user — and no OAuth grant that
would make one possible. If you're reaching for a background job over user data, re-read
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Phase

| Phase | State |
|---|---|
| **Now** | `/health` only. `app/{api,routes,models}/` exist and are empty — that's the intended shape, not an oversight. |
| **Phase 1** | `POST /orders/ingest` — Bedrock extraction, urgency ranking. **There is no `GET /orders`.** The ranked list comes back in the ingest response and the extension stores it. |
| **Phase 2** | Pickup endpoints — eligibility, schedule, refresh, cancel. Gated on USPS API access, so build behind a mock adapter with the same interface; switching to live is a base URL and a credential. |
| **Later** | Deployment to Lambda. **No datastore is planned** — see the persistence rule below. |

## Commands

```bash
uv sync
uv run fastapi dev app/main.py     # :8000
```

`uv` manages this workspace. Don't introduce `pip` or `requirements.txt`. Python 3.13.

## Conventions

**Bedrock access goes through `app/bedrock.py`** — a single cached `AsyncAnthropicBedrockMantle`.
Never construct a second client, never hardcode a region. Credentials resolve through the standard
AWS chain: env vars locally, the Lambda execution role in production.

**Address the model by its regional inference profile, not a bare model ID.** Recent Anthropic
models on Bedrock are invocable only through a `us.`-prefixed profile identifier; a bare
`anthropic.<model>` raises a validation error *at invoke time* — on a user's first parse, inside a
Lambda — rather than at deploy. `BEDROCK_MODEL` therefore has **no default in code** and is
validated at startup; don't add one back. Find the right string with
`aws bedrock list-inference-profiles --region $AWS_REGION`. Call `bedrock.model("parse")` or
`bedrock.model("action")` rather than reading a constant — the two call sites have different
latency budgets (NFR-6.4) and may be configured to different models.

**Cold-start work belongs in the FastAPI `lifespan`, and Mangum's lifespan handling must stay on.**
Mangum is the ASGI-to-Lambda adapter; it runs lifespan startup once per cold start. The model
config check lives there now and the SSM credential fetch will. Turn lifespan off and none of it
runs — no error, just a Parameter Store round trip on every request and a validation that never
fires.

**Error shape.** One shape everywhere, because the agent has to say something useful to a human:

```jsonc
{
  "reason": "kebab-case-code",
  "message": "One sentence a human can act on.",
  "request_id": "opaque identifier for this request"
}
```

`request_id` goes on **every** response, success or failure, and on **every** log line. It is the
only correlator that survives the logging rule below — with order contents, titles, addresses and
confirmation numbers all unloggable, there is otherwise nothing tying a user's report to a log.
Keep it opaque; it is not a session ID and nothing should correlate two requests from one install.

| `reason` | Meaning |
|---|---|
| `unrecognized-page` | DOM didn't parse as an order page |
| `wrong-carrier-label` | Label is prepaid, but not with USPS postage — no USPS pickup |
| `address-not-serviceable` | USPS pickup unavailable at this address |
| `location-not-serviceable` | Carrier can't honour the stored package location |
| `etag-expired` | Refresh the pickup before amending or cancelling |
| `upstream-unavailable` | USPS or Bedrock failed; safe to retry |
| `payload-too-large` | Ingest subtree exceeded the configured ceiling |

A bare status code is not enough — the UI branches on `reason`.

**There is no `qr-only` error.** A retailer offering a free QR drop-off is a *success* — the return
completes, it just skips the pickup step. Treating it as a failure was a real bug in an earlier
draft: it pushed the flow toward buying a paid printable label to satisfy our own pickup
precondition, out of the user's refund.

## Rules specific to this workspace

- **Eligibility before scheduling, always.** No caching across addresses, no "we checked earlier."
- **Return the `confirmationNumber` and `ETag` to the caller; store neither.** The extension keeps
  the confirmation number and the address it was booked against.
- **Never treat a stored ETag as usable.** It is good for one hour or one use, so a cancellation the
  next day always refreshes the pickup first to obtain a current one, then cancels. That is why
  `POST /pickups/{confirmation_number}/refresh` exists. Assuming a stored ETag still works is the
  part most integrations get wrong.
- **Set `packageType: "RETURNS"` and `nextAvailablePickup: true`** on schedule calls, so an
  unserviceable day rolls forward instead of failing.
- **Use the standardized address** the eligibility call returns — not what the user typed.
- **Reject `labelPrinted: false`** for pickup scheduling. Enforce it here rather than trusting the
  caller to remember (D6).
- **Check *whose* postage is on the box, not just that a label exists.** A printed UPS or FedEx
  label satisfies "a label was printed" and will still never be collected — a USPS carrier is
  collecting mail. The return request carries `label_carrier`; anything other than USPS is
  `wrong-carrier-label`, not a scheduling attempt.
- **Package location is a neutral vocabulary, not a carrier's enum.** The API accepts
  `front_door | back_door | side_door | knock_or_ring | mailbox | reception | other` plus a free-text
  note; the carrier adapter maps it and declares what it cannot serve. Don't store a vendor's
  spelling in user data — USPS has ~9 values with required special instructions, FedEx a 4-value
  enum, UPS free text; they do not reconcile. `mailbox` in particular is **not portable by law** —
  18 U.S.C. § 1725 reserves mailboxes to the Postal Service, so a UPS or FedEx driver cannot honour
  it whatever their API accepts. That's a `location-not-serviceable`, surfaced before scheduling.
- **Keep ingestion payloads small.** The extension sends an order-list subtree, not a page, and
  caps itself at `MAX_INGEST_BYTES` before sending. Enforce the ceiling here as well —
  `payload-too-large` — because the client-side cap is a courtesy, not a control, on an
  unauthenticated endpoint. If a caller sends more, that's a bug on their side worth pushing back
  on; it's also the thing a Chrome Web Store reviewer will ask about.
- **The return-flow endpoints are a second DOM egress path, and they are bound by the same rules.**
  Ingestion is not the only thing that sends page content. **The label page is never transmitted** —
  it carries the tracking number and the address, and nothing about parsing it requires a round
  trip.
- **`max_tokens` is bounded and the timeout is short.** `BEDROCK_MAX_TOKENS = 4096`, 60 s. These
  are cost controls on an endpoint anyone can call, not performance tuning.
- **Never log order contents, item titles, addresses, or confirmation numbers — at any level,
  `DEBUG` included.** Structured orders are user data, and `LOG_LEVEL` is a runtime parameter, so a
  level-scoped rule is one config change away from writing home addresses into CloudWatch. Enforce
  it with a redacting formatter, not at the call site. Log field presence, lengths and validation
  outcomes instead.
- **Log the `request_id` on every line.** See the error shape above; it is what makes the redaction
  rule survivable during an incident.

## Gotchas

- **The USPS spec is inconsistent about scope naming**: operations declare `carrier-pickup`, the
  security scheme block says `pickup`. Don't assume — log the granted scope on the first
  successful call.
- **`apis-tem.usps.com` mirrors production** and takes the same client ID and secret. Only the
  base URL changes, so there's no separate sandbox credential to manage.
- **Legacy USPS Web Tools (`ShippingAPI.dll`) was retired 25 Jan 2026.** Ignore every tutorial
  that uses it.
- **Return windows are inferred and often wrong at the edges** — retailers vary policy by
  category, sale status and membership tier. Return them as a prompt to act, never a guarantee.
- **Return the `return_by` date, never a countdown.** "4 days left" computed on the server is frozen
  the moment it's stored and silently wrong the next morning — which defeats the one thing the
  product is for. The client derives urgency at render from the date.
