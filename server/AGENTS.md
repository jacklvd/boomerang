# server/AGENTS.md

FastAPI service. Read [`../AGENTS.md`](../AGENTS.md) first for repo-wide rules.

## Scope

The server is a **stateless broker and inference host**. It:

- turns messy order-page DOM into structured orders, via Bedrock
- ranks orders by return-window urgency
- brokers USPS eligibility and pickup scheduling
- holds every credential in the system

It does **not** own a browser, touch a retailer session, or hold a user credential.

**The server never initiates anything.** Every code path starts with a request from the extension
or the dashboard. There is no poller, no scheduler, no webhook to a user — and no OAuth grant that
would make one possible. If you're reaching for a background job over user data, re-read
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Phase

| Phase | State |
|---|---|
| **Now** | `/health` only. `app/{api,routes,models}/` exist and are empty — that's the intended shape, not an oversight. |
| **Phase 1** | `POST /orders/ingest` + `GET /orders` — Bedrock extraction, urgency ranking. |
| **Phase 2** | Pickup endpoints — eligibility, schedule, cancel. Gated on USPS API access, so build behind a mock adapter with the same interface; switching to live is a base URL and a credential. |
| **Later** | A real datastore. Losing an ETag means losing the ability to cancel a pickup, so in-memory state stops being adequate the moment a second person uses this. |

## Commands

```bash
uv sync
uv run fastapi dev app/main.py     # :8000
```

`uv` manages this workspace. Don't introduce `pip` or `requirements.txt`. Python 3.13.

## Conventions

**Bedrock access goes through `app/bedrock.py`** — a single cached `AsyncAnthropicBedrockMantle`.
Never construct a second client, never hardcode a region. Credentials resolve through the standard
AWS chain: env vars locally, the EC2 instance role in production.

**Model IDs on Bedrock carry an `anthropic.` prefix** (`anthropic.claude-opus-5`); first-party IDs
do not. Read it from `BEDROCK_MODEL`, don't inline it.

**Error shape.** One shape everywhere, because the agent has to say something useful to a human:

```jsonc
{ "reason": "kebab-case-code", "message": "One sentence a human can act on." }
```

| `reason` | Meaning |
|---|---|
| `unrecognized-page` | DOM didn't parse as an order page |
| `qr-only` | Retailer issued a QR code, not a printable label |
| `address-not-serviceable` | USPS pickup unavailable at this address |
| `etag-expired` | Refetch the pickup before amending |
| `upstream-unavailable` | USPS or Bedrock failed; safe to retry |

A bare status code is not enough — the UI branches on `reason`.

## Rules specific to this workspace

- **Eligibility before scheduling, always.** No caching across addresses, no "we checked earlier."
- **Persist `confirmationNumber` and `ETag` together.** The ETag is good for one hour or one use
  and is required for both amend and cancel. This is the part most integrations get wrong.
- **Set `packageType: "RETURNS"` and `nextAvailablePickup: true`** on schedule calls, so an
  unserviceable day rolls forward instead of failing.
- **Use the standardized address** the eligibility call returns — not what the user typed.
- **Reject `labelPrinted: false`** for pickup scheduling. Enforce it here rather than trusting the
  caller to remember (D6).
- **Keep ingestion payloads small.** The extension sends an order-list subtree, not a page. If it
  sends more, that's a bug on their side worth pushing back on — it's also the thing a Chrome Web
  Store reviewer will ask about.
- **Never log order contents or addresses** at info level. Structured orders are user data.

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
