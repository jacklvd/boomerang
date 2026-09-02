# Architecture & Decisions

How the pieces fit, and the settled decisions behind the shape. **Read the relevant decision
before proposing an alternative** — these were expensive to establish. Sources in
[`../.claude/artifacts/`](../.claude/artifacts/).

> This document is the *why*. The *what to build* is
> [`../design/boomerang-requirements.md`](../design/boomerang-requirements.md) and
> [`../design/boomerang-high-level-design.md`](../design/boomerang-high-level-design.md), which
> refine several decisions here — notably a stateless server on Lambda with no VPC and no
> database. Where they disagree with this file, they win; the decision text below is annotated
> where that has happened.

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
│  holds all API keys  │──►│ configured        │
└──────────┬───────────┘   │ third-party pickup│
           ▼               └──────────────────┘
┌──────────────────────┐
│ client (Next.js)     │  landing · install funnel · dashboard
└──────────────────────┘
```

**Extension** — the only component with access to user data. Reads order pages, drives the
return flow, opens the calendar tab, requests retailer permissions in context. Holds **no**
carrier or retailer credentials.

**Server** — stateless broker and inference host. Parses DOM via Bedrock, ranks urgency, brokers
configured third-party pickup calls, holds every credential. **Never initiates anything.**

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

1. On first interaction, the extension records optional return preferences: return address, preferred
   self-service drop-off or home pickup, and printer access. Preferences stay in client storage.
2. User picks an order and confirms intent.
3. Extension requests host permission for that retailer if not already granted (D7).
4. Return driver navigates the retailer's return flow, from configured selectors first and the
   model only on a miss. At the choice of return method it stops and presents every option with its
   price (FR-3.3.4). Free drop-off ends here, successfully. A printable label continues → **printed
   label** + tracking number + which carrier's postage it is (D6).
5. Server calls the selected supported third-party carrier's eligibility for the user's address.
   **Hard gate** (D5). Ineligible → keep the retailer's own drop-off options visible. Never
   auto-escalate.
6. Server schedules the pickup and returns the `confirmationNumber` and `ETag` to the extension,
   which stores the confirmation number and the address it was booked against (D5).
7. Extension opens the prefilled calendar URL; user reviews and saves (D2).
8. Confirmation copy names the day the configured carrier returned — never a time window, never a
   guarantee (D6).

## Trust boundary

| Data | Lives where | Notes |
|---|---|---|
| Order page DOM | Extension → server → Bedrock | Transient; not persisted raw |
| Return-flow step DOM | Extension → server → Bedrock | Fallback path only, when no selector matches. Same minimisation rules |
| Label page DOM | Extension only | Never transmitted — it carries the tracking number and return address |
| Structured orders | Extension (`chrome.storage.local`) | Returned in the ingest response; the server keeps nothing |
| Retailer session | Browser only | Content script runs in the user's own session; we never see credentials |
| Configured carrier credentials | Server only | App-level credentials, not per-user |
| Pickup confirmation + address | Extension | The ETag is passed through and deliberately not stored |
| Google account | Nowhere | No scopes requested at all |
| Item + address → Google | Sent in the calendar template URL | We hold nothing of Google's; we do send this to them. Stated rather than implied |

The extension never holds an API key; the server never holds a user credential. Neither can be
compromised into the other's capabilities.

---

# Decisions

## D1 — Read retailer order pages, not Gmail

Order ingestion comes from a content script reading retailer "Your Orders" pages. Gmail is out of
scope in every form, API and scraping alike.

The first reason survives every other one: **Gmail is the wrong page to read even if it were
free.** A receipt email tells you an order happened, not whether it can still be returned. The
order page carries authoritative status, return eligibility, and the entry point into the return
flow — the three things the agent acts on. There is shipped Chrome Web Store precedent for the
technique.

Every Gmail scope that reads content or metadata is *restricted* — including `gmail.metadata`
(downgrading from `gmail.readonly` buys a narrower footprint and an easier story, not a cheaper
process). That means app verification, then a CASA security assessment: ~$540–$1,800/yr in
perpetuity, 6–12 weeks before the first outside user, annual revalidation forever.

The trigger clause is specific: an app that "accesses or **has the capability to access** Google
user data from or through a server" needs the annual third-party assessment. Our FastAPI service
forwarding content to Bedrock lands squarely inside it, and "we don't persist anything" doesn't
help.

Scraping `mail.google.com` needs no scope, and skipping the API is not escaping policy. Chrome Web
Store **Limited Use** governs every byte of user data the extension handles, not only data
obtained through a Google API, and tightened on 1 August 2026: collection must be strictly
necessary to the single disclosed purpose, cross-purpose reuse prohibited, prominent disclosure
for every collection. "Strictly necessary to a returns tool" is arguable for an orders page and a
far harder case for a user's entire inbox.

Web Store review is the only distribution gate — there is no second channel — and the Bedrock
hop is already the hardest question in ours, since comparable order-scraping extensions advertise
that they run locally and send nothing anywhere. A `mail.google.com` host permission combines that
with the broad-host-permission flag that draws in-depth review, on a DOM with the same obfuscated
virtualized character D3 refuses in Calendar.

*Costs us:* no ambient inbox awareness. We learn about an order when the user visits the order page.
*Reopens if:* unattended background monitoring becomes non-negotiable — ambient awareness is the
one thing an order page structurally cannot provide, and no parser improves it into existence.

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

## D4 — Third-party pickup, with USPS first

USPS is the first concrete adapter. Other carriers are enabled only when their credentials and
documented pickup contract are available; the retailer's actual return option determines which
carrier can be used.

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

## D5 — Eligibility is a hard gate; the ETag is refreshed, never stored

Eligibility runs before every schedule call, no exceptions. The extension stores the
`confirmationNumber` and the address it was booked against; nobody stores the `ETag`.

Eligibility is address-specific, so a meaningful share of users get a no — the agent needs a
graceful second answer, not an error. Amend and cancel both require an ETag, but it is good for
one hour or one use, so a stored one is worthless by the time the user changes their mind. The
correct pattern is refresh-then-cancel: re-read the pickup to obtain a current ETag, then act on
it. Treating a stored ETag as usable is the part most integrations get wrong.

*Superseded detail:* this decision originally had the server persist both values. The server is
now stateless — see [`../design/boomerang-high-level-design.md`](../design/boomerang-high-level-design.md) §6.3.

## D6 — The label must be printed before the pickup call

A pickup needs a printed label on the box, not a QR code. USPS Free Package Pickup only covers
packages with prepaid postage affixed; a pickup for an unlabeled box isn't legitimate. And the
postage must be **USPS** postage — the letter carrier is collecting mail, so a prepaid UPS label
will not be collected however printed it is.

Related copy constraint: free pickup happens on the normal delivery round, Mon–Sat — a **day, not
a window**, and never a guarantee. Never auto-escalate to a paid option.

*Superseded details:* two, both in
[`../design/boomerang-requirements.md`](../design/boomerang-requirements.md).

The driver no longer *selects* the printable label. Where a retailer offers a choice it presents
every option with its price and stops (FR-3.3.4) — on Amazon the printable label is often a paid
refund deduction while the QR drop-off is free, so auto-selecting it to satisfy this decision's own
precondition would spend the user's money to reach a pickup they never asked for. A QR drop-off is
now a successful outcome, not the `qr-only` error.

The mandated phrase "with tomorrow's mail delivery" is withdrawn (FR-3.4.7). It was wrong at three
edges: same-day requests before 2:00 AM CT are collected *today*, Sundays and holidays roll forward,
and `nextAvailablePickup` can roll past an unserviceable day. USPS returns the scheduled date; copy
renders it. The day-not-a-window invariant is unchanged.

## D7 — Minimal manifest, permissions requested in context

The manifest declares `activeTab`, `scripting` and `storage`. Retailer domains go in
`optional_host_permissions`, requested when the user names the retailer.

*Superseded detail:* this decision originally said `activeTab` and `scripting` only, which forbade
the permission every stored entity depends on, and it had no first-run story —
`activeTab` grants access only on a user gesture, so an extension holding it alone can never ingest
on page load, and one holding no host permission has nothing to escalate from. The two-tier
acquisition that fixes it is FR-3.7.2: a "Scan this page" click first, the standing grant offered
only after the user has seen it work. The manifest also pins a generated `key` so the extension ID
is stable enough to allowlist — see
[`../design/boomerang-high-level-design.md`](../design/boomerang-high-level-design.md) §6.6.

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
