# Architecture & Decisions

How the pieces fit, and the settled decisions behind the shape. **Read the relevant decision
before proposing an alternative** — these were expensive to establish. Sources in
[`../.claude/artifacts/`](../.claude/artifacts/).

## The one thing to understand first

Boomerang holds **no OAuth grant for any user**. The backend has no independent path to user
data: it cannot poll, cannot run a nightly job, cannot check anything while the user is away.
Every byte the server sees arrived because the extension pushed it during a session where the
user was present.

If a feature needs the server to know something the extension never sent, that feature needs a
different design — not a background worker.

## Components

```
┌─────────────────────────────────────────────────────────────┐
│ BROWSER                                                     │
│  ┌───────────────┐   reads DOM    ┌──────────────────────┐  │
│  │ content       │◄───────────────│ retailer order page  │  │
│  │ script        │                │ (user's own session) │  │
│  └───────┬───────┘                └──────────────────────┘  │
│  ┌───────▼───────┐   opens tab    ┌──────────────────────┐  │
│  │ service       │───────────────►│ calendar template URL│  │
│  │ worker        │                │ (no host permission) │  │
│  └───────┬───────┘                └──────────────────────┘  │
│  ┌───────▼───────┐                                          │
│  │ popup         │  order list, urgency, "return this"      │
│  └───────┬───────┘                                          │
└──────────┼──────────────────────────────────────────────────┘
           │ HTTPS  ── the only data path off the client ──
           ▼
┌──────────────────────┐   ┌──────────────────┐
│ server (FastAPI)     │──►│ Bedrock (Claude) │  DOM → structured
│  parse · rank        │   └──────────────────┘
│  carrier broker      │   ┌──────────────────┐
│  holds all API keys  │──►│ USPS Carrier     │
└──────────┬───────────┘   │ Pickup           │
           ▼               └──────────────────┘
┌──────────────────────┐
│ client (Next.js)     │  landing · install funnel · dashboard
└──────────────────────┘
```

**Extension** — the only component with access to user data. Reads order pages, drives the
return flow, opens the calendar tab, requests retailer permissions in context. Holds **no**
carrier or retailer credentials.

**Server** — stateless broker and inference host. Parses DOM via Bedrock, ranks urgency, brokers
USPS calls, holds every credential. **Never initiates anything.**

**Client** — landing page, email subscribe, install funnel, post-install dashboard.

## Data flow: ingestion

1. User navigates to a retailer order page they're already logged into.
2. Content script waits for render (`MutationObserver` — order pages are SPAs and a single read
   at `document_idle` will flake) and extracts the order-list subtree.
3. Service worker posts it to `POST /orders/ingest`.
4. Server sends it to Bedrock with a retailer-specific extraction prompt, gets structured orders
   back, computes return-window urgency, returns the ranked list.
5. Popup renders it.

**Design note.** Sending DOM to Bedrock rather than parsing in the extension is the choice that
draws Chrome Web Store reviewer attention — comparable extensions advertise that they run locally
and send nothing anywhere. It buys resilience against DOM churn, the single largest maintenance
risk in the product. Keep the payload minimal: the order-list subtree, not the whole page. If the
review narrative becomes a problem, on-device extraction with only derived facts (retailer, date,
order ID) crossing to the backend is the fallback — a different product, but a real one.

## Data flow: return + pickup

1. User picks an order and confirms intent.
2. Extension requests host permission for that retailer if not already granted (D7).
3. Return driver navigates the retailer's return flow → **printed label** + tracking number (D6).
4. Server calls USPS eligibility for the user's address. **Hard gate** (D5). Ineligible → offer
   nearest drop-off or a priced alternative with the price stated. Never auto-escalate.
5. Server schedules the pickup, persists `confirmationNumber` **and** `ETag` together (D5).
6. Extension opens the prefilled calendar URL; user reviews and saves (D2).
7. Confirmation copy: "with tomorrow's mail delivery" — never a time window (D6).

## Trust boundary

| Data | Lives where | Notes |
|---|---|---|
| Order page DOM | Extension → server → Bedrock | Transient; not persisted raw |
| Structured orders | Server | The working set |
| Retailer session | Browser only | Content script runs in the user's own session; we never see credentials |
| USPS credentials | Server only | App-level client-credentials OAuth, not per-user |
| Pickup confirmation + ETag | Server | Must persist together |
| Google account | Nowhere | No scopes requested at all |

The extension never holds an API key; the server never holds a user credential. Neither can be
compromised into the other's capabilities.

---

# Decisions

## D1 — Read retailer order pages, not Gmail

Order ingestion comes from a content script reading retailer "Your Orders" pages. Gmail is out of
scope in every form, API and scraping alike.

Every Gmail scope that reads content or metadata is *restricted* — including `gmail.metadata`
(downgrading from `gmail.readonly` buys a narrower footprint and an easier story, not a cheaper
process). That means app verification, then a CASA security assessment: ~$540–$1,800/yr in
perpetuity, 6–12 weeks before the first outside user, annual revalidation forever.

The trigger clause is specific: an app that "accesses or **has the capability to access** Google
user data from or through a server" needs the annual third-party assessment. Our FastAPI service
forwarding content to Bedrock lands squarely inside it, and "we don't persist anything" doesn't
help.

Order pages are also better on the merits — authoritative status, return eligibility, and the
entry point to the return flow, none of which a receipt email has. There is shipped Chrome Web
Store precedent for the technique.

*Costs us:* no ambient inbox awareness. We learn about an order when the user visits the order page.
*Reopens if:* unattended background monitoring becomes non-negotiable, or per-retailer parser
maintenance outgrows the annual fee.

## D2 — Write calendar events through a prefilled URL

`https://calendar.google.com/calendar/render?action=TEMPLATE` with `text`, `dates`, `ctz`,
`details`, `location`. The user sees their own calendar with the form filled in and clicks Save.
`.ics` fallback for non-Google users.

No OAuth scope, no SDK, no credential. And `chrome.tabs.create({url})` needs **no host permission
at all** — host permissions gate script injection, fetch, and reading sensitive tab properties,
not navigation. So we write to Calendar while requesting nothing for `google.com`.

The confirmation click isn't friction. It *is* the "ping," and it makes the agent's action
reviewable before it commits.

## D3 — Don't read calendar availability

The agent proposes a pickup day from the carrier's slots. It does not determine when the user is
free.

There's no scrape-free way to read Calendar, and `calendar.google.com` is an obfuscated
virtualized SPA whose DOM would be the most fragile surface in the product. Designing the
requirement away is strictly better: when the prefilled tab opens, the user sees the proposed
block rendered in their own calendar, in their own timezone. They spot a conflict faster than any
parser, and moving the event is a drag.

## D4 — USPS only for carrier pickup in v1

UPS is a fast-follow behind a flag. FedEx is not integrated.

Our user is a consumer holding a retailer-issued prepaid label. They will never have a UPS or
FedEx shipper number, and asking kills the product. That single constraint decides it:

| | Schedule without a shipper account? |
|---|---|
| **USPS** | **Yes** — the request body has no account field of any kind |
| UPS | Conditionally — `Shipper` is optional if you pay by tracking number or card |
| FedEx | No — `associatedAccountNumber` is required and is the account invoiced |

The USPS `SchedulePickupRequest` has no `accountNumber`, no CRID, no MID, no payment token. The
pickup binds to the consumer's address and their own email or SMS contact; the only thing
authenticated is *our app*. Scheduling on a user's behalf isn't a workaround — it's the ordinary
shape of the API. And it's free on both sides.

UPS is workable via `PaymentMethod 04` (bill the pickup to the retailer's 1Z return tracking
number, ≤30 per pickup) but you need a UPS account just to get credentials, and a refused payment
leaves us owing ~$9–15. FedEx has no tracking-number payment path at all; its fallback is the
fedex.com guest flow through the browser we already drive.

*Rejected: shipping aggregators.* EasyPost and Shippo both bind a pickup to a shipment *you*
created on *your* carrier account. A retailer-issued label is neither. They add cost and a
dependency without removing the account requirement.

## D5 — Eligibility is a hard gate; ETag stored with the confirmation

Eligibility runs before every schedule call, no exceptions. `confirmationNumber` and `ETag`
persist together.

Eligibility is address-specific, so a meaningful share of users get a no — the agent needs a
graceful second answer, not an error. And amend/cancel both require the ETag, good for one hour
or one use. Without it stored, the user cannot cancel — and they will want to. This is the part
most integrations get wrong.

## D6 — The label must be printed before the pickup call

The return flow ends at a printed label on the box, not a QR code. USPS Free Package Pickup only
covers packages with prepaid postage affixed; a pickup for an unlabeled box isn't legitimate.

Related copy constraint: free pickup happens on the normal delivery round, Mon–Sat — a **day, not
a window**. Same-day requests must land before 2:00 AM CT. All user-facing copy says "with
tomorrow's mail delivery." Never auto-escalate to a paid option.

## D7 — Minimal manifest, permissions requested in context

The manifest declares `activeTab` and `scripting`. Retailer domains go in
`optional_host_permissions`, requested when the user names the retailer.

Broad host permissions — especially `<all_urls>` — flag an extension for in-depth Chrome Web
Store review and often a return for revision. The quality FAQ's own example is a shopping
extension with an action button plus host access on the store being browsed; "e-commerce returns"
is the same shape and is defensible, but must be argued in the listing rather than assumed.

---

## Open questions

- **Which retailer for the PoC.** Amazon has the best-documented order-page DOM and published
  scraping precedent; J.Crew carries the demo narrative and a simpler return flow. Ingestion is
  easy either way — the return-flow drive is the risky half and should decide it.
- **Model-training stretch goal.** Chrome Web Store Limited Use has no equivalent of the
  Workspace model-training prohibition, which attaches to data obtained through Google APIs. Data
  read off a retailer's page isn't covered — so it's a disclosure question, not a prohibition.
  Out of PoC scope regardless.
- **On-behalf scheduling is unobjected-to, not blessed.** Nothing in the USPS API terms prohibits
  it, and USPS's own material frames the APIs as serving "you and your customers." Worth written
  confirmation from USPS API support before scaling, and worth capturing explicit per-pickup user
  consent either way.
