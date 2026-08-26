# Boomerang — The "Reverse-Logistics" Concierge

*An everyday agent that handles e-commerce returns end-to-end.*

> **Status:** PoC. Product sketch — what we're building and why.
> Architecture and settled decisions: [`ARCHITECTURE.md`](ARCHITECTURE.md).
> The buildable spec lives in [`../design/`](../design/) —
> [requirements](../design/boomerang-requirements.md) and
> [high-level design](../design/boomerang-high-level-design.md). Where this sketch and those
> disagree, they win.
> Research sources: [`../.claude/artifacts/`](../.claude/artifacts/). Implementation tickets land
> in [`../.claude/tickets/`](../.claude/tickets/) when the next phase starts.

---

## 1. The Problem

E-commerce returns are a massive source of personal friction. You buy clothes, they don't fit, and you lose $50 because you forgot to:

1. Navigate the return portal
2. Print the label
3. Drop off the box within the 30-day window

---

## 2. How It Works

**1. Ambient order awareness** — A browser extension reads the retailer order pages you already
visit, extracts what you bought and when, and tracks the return window.

**2. Triggered action** — You tell the agent:
> "Return the blue sweater from the J.Crew order."

The agent walks the retailer's return flow — reason code, label generation — and stops where the
retailer offers a choice of return methods, showing you each one **with its price**. Free carrier
pickup requires prepaid USPS postage on the box, so it needs a printed label; but the printable
label is sometimes the paid option, and that's your call to make, not the agent's.

**3. The magic** — It checks USPS pickup eligibility for your address, schedules a free Carrier
Pickup for the next delivery day, and opens a prefilled calendar event so you remember to put
the box out.

**4. The ping**
> "I set up the J.Crew return. Your carrier will collect it with Wednesday's mail — leave the box out with the printed label on it before your usual delivery time."

The day comes from USPS's own response, not from an assumption. Usually it's tomorrow; before 2 AM
Central it's today; on a Saturday evening it's Monday.

---

## 3. What Research Changed

Two briefs were written against the original sketch and moved five things. Each is load-bearing.
Full reasoning in [`ARCHITECTURE.md`](ARCHITECTURE.md); sources in
[`../.claude/artifacts/`](../.claude/artifacts/).

| Originally | Now | Why |
|---|---|---|
| Gmail API monitors the inbox | Content script reads **retailer order pages** | Every useful Gmail read scope is *restricted* — verification + CASA assessment, ~$540–$1,800/yr forever, 6–12 weeks before the first outside user. An extension reading rendered DOM needs no OAuth scope at all. Order pages also carry better data than receipts. |
| Calendar API writes the reminder | **Prefilled `render?action=TEMPLATE` URL** | No scope, no host permission, no SDK. The user reviews and saves — which is also the consent moment. |
| Agent reads calendar for availability | Agent **proposes**, user's eyes are the check | No scrape-free way to read Calendar, and its DOM is the most fragile surface in the product. |
| "Porch pickup tomorrow, 9 AM–12 PM" | The **day USPS returns**, named plainly | Free USPS pickup is a **day, not a window**. The two-hour guarantee is a different product, ~$25. And "tomorrow" is itself a guess — the cutoff, Sundays and holidays all move it. |
| USPS/UPS, carrier unspecified | **USPS only for v1** | USPS is the only carrier whose pickup request has no account field at all. Our user is a consumer with a retailer-issued label; they'll never have a UPS or FedEx account. |

One consequence reshapes the architecture rather than a feature: **with no OAuth grant, the
backend can never see anything on its own.** Every byte reaches FastAPI because the extension
pushed it. "Passive monitoring" becomes "runs when the user is there."

---

## 4. User Flow

```
                  Landing page (Next.js)
                          │
                          ▼
                  Install extension  ← the only permission prompt
                          │
                          ▼
        ┌─── User browses a retailer order page ───┐
        │                                          │
        ▼                                          │
  Content script reads the rendered DOM            │  (repeats; no
        │                                          │   background
        ▼                                          │   access)
  POST /orders/ingest  →  Bedrock parses           │
        │                                          │
        ▼                                          │
  Orders ranked by return-window urgency ──────────┘
        │
        ▼
  User: "return the blue sweater from J.Crew"
        │
        ▼
  Request host permission for that retailer, in context
        │
        ▼
  Drive the return flow → present every option with its price
        │
        ├─ free drop-off ──► done, no pickup needed
        │
        ▼
  Printed label + tracking number + which carrier's postage
        │
        ▼
  USPS eligibility check   ← hard gate, never skipped
        │
        ├─ ineligible ──► offer nearest drop-off, or priced UPS
        │
        ▼
  Schedule pickup → extension stores confirmationNumber + address
        │
        ▼
  Open prefilled Calendar URL → user reviews → Saves
        │
        ▼
  Confirmation names the day USPS returned
```

The first run is different: `activeTab` can't inject on page load, so the popup offers **"Scan this
page"** and the standing permission is offered afterwards, once the user has seen it work.

---

## 5. Technical Implementation

| Surface | Role |
|---|---|
| **Extension** (MV3) | Reads order pages, drives the return flow, opens the calendar URL. The only component with access to user data. |
| **Client** (Next.js) | Landing page, install funnel, order dashboard. |
| **Server** (FastAPI) | Parses order DOM via Bedrock, ranks urgency, brokers carrier calls, holds the API keys. Sees only what the extension sends. |

| Layer | Stack |
|---|---|
| Extension | TypeScript, Manifest V3, content scripts + `chrome.scripting` |
| Front-end | TypeScript / Next.js 16 + shadcn-ui + Base UI + Tailwind 4 |
| Back-end | FastAPI + Bedrock (Claude Opus 5) |
| Infra | Terraform — Lambda + Function URL, SSM Parameter Store, CloudWatch. No VPC, no database. |

```
extension/   MV3 extension     (to build)
client/      Next.js app       (scaffolded)
server/      FastAPI service   (scaffolded)
infra/       Terraform         (EC2 scaffold, superseded by the Lambda design)
```

Each workspace has its own `AGENTS.md` with scope, phase, and local conventions.

---

## 6. PoC Scope

**In:** one retailer end to end — ingestion → urgency ranking → assisted return flow → USPS
eligibility + pickup (mocked until API access lands) → prefilled calendar event.

**Out, deliberately:** Gmail in any form. A second retailer. UPS/FedEx fallbacks. Unattended
background monitoring. Teaching the model receipt patterns.

**Critical path:** USPS Carrier Pickup isn't in the default API access package and USPS warns of
extended wait times. Filing the access request is the one task that can't be parallelized away —
do it before writing the client, and build against a mock adapter while it sits in the queue.

---

## 7. Agent Tools

| Tool | Description |
|---|---|
| **Order Gatherer** | Parse order-page DOM into structured orders; rank by return-window urgency |
| **Return Driver** | Navigate the retailer's return flow to a printed label + tracking number |
| **Pickup Scheduler** | USPS eligibility → schedule → extension stores `confirmationNumber` + address; refresh before any cancel |
| **Calendar Writer** | Build the prefilled Calendar template URL, or an `.ics` fallback |

---

## 8. Compliance Posture

The extension route escapes Google's restricted-scope regime, but not policy in general. Chrome
Web Store **Limited Use** governs all user data an extension handles — not just data from Google
APIs — and tightened on **1 August 2026**: collection must be strictly necessary to the single
disclosed purpose, cross-purpose reuse is prohibited, every collection needs prominent disclosure.

- **The Bedrock hop is what a reviewer will ask about.** Comparable order-scraping extensions
  advertise that they run locally and send nothing anywhere. We differ; disclose it loudly.
- **Keep host permissions small.** Broad `<all_urls>` flags in-depth review. Ship `activeTab`,
  `scripting` and `storage`; request retailer domains in context, after the first successful scan.
- **Chrome Web Store review is the only distribution gate.** There is no second channel.
