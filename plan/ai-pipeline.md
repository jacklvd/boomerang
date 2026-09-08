# Boomerang AI Pipeline Specification (v1)

## Table of Contents
1. [System Boundaries & Invariants](#1-system-boundaries--invariants)
2. [User Preferences Model](#2-user-preferences-model)
3. [End-to-End Pipeline Architecture](#3-end-to-end-pipeline-architecture)
4. [Detailed Pipeline Stages](#4-detailed-pipeline-stages)
5. [Decisions Recorded](#5-decisions-recorded)

---

## 1. System Boundaries & Invariants

| Invariant | Description |
|---|---|
| **Stateless Server Architecture** | The FastAPI backend holds zero database records, session cookies, or user profile tables. |
| **Active Tab WebMCP Execution** | The Strands Agent drives the return flow directly inside the user's active browser session via WebMCP. No headless server-side browser runs, eliminating the need to store user passwords or retailer session tokens. |
| **User-Initiated Ingestion** | The extension reads retailer order page subtrees only after explicit user action (icon click), never ambiently on page load. Ambient background scraping and inbox monitoring are strictly out of scope (**Decision D1**). |
| **Zero OAuth Scope Handoff** | Calendar events are scheduled using standard browser template URLs (`action=TEMPLATE`), requiring zero Google OAuth tokens or scopes (**Decision D2**). |
| **Policy Verification Without Defaulting** | The system never defaults to an assumed 30-day return window. If the order DOM lacks explicit rules, the agent autonomously retrieves the merchant's live policy before displaying options. |
| **Client-Side Session Continuity** | In-progress return context (selected items, chosen return option, form state) **and** the user's preference priority order persist in browser `localStorage` or a synced extension storage API — never on the server. This does not violate the stateless-server invariant since none of it leaves the client until final submission. |
| **Preference-Driven, Not Auto-Decided** | Ranking return options by user preference informs *ordering and pre-selection* of options shown to the user — it never silently submits a return method without the human-in-the-loop confirmation gate. |

---

## 2. User Preferences Model

The ranking stage weighs return options against a small set of user-declared or inferred preferences. These are set as a **fixed priority order at signup** and can be edited by the user at any time thereafter; the order can also be overridden per individual return.

| Preference | What It Optimizes For | Downstream Effect |
|---|---|---|
| **Save the most money** | Lowest total cost (label fees, restocking fees) | Ranks free QR drop-off and no-fee options highest; deprioritizes paid pickup/label options |
| **Return as fast as possible** | Speed of resolution / fastest refund-triggering method | Ranks options by carrier transit time and drop-off availability rather than cost |
| **Sustainability-conscious** | Minimizing shipping/packaging footprint | Prioritizes in-store or partner QR drop-off over shipped-label pickup when both are available |
| **No printer access** | Feasibility given user's hardware | Deprioritizes the printed-label pickup path in ranking so QR-only options surface first; if the user still selects a carrier pickup path, printer/fee confirmation happens as part of the AI-driven info-gathering step in Stage 7 |

**Ranking logic:** each available return method (QR drop-off, printed label + drop-off, printed label + porch pickup) is scored against the active preference(s) rather than treated as a single default. If preferences conflict (e.g., "fastest" vs. "no printer" when the fastest option requires a label), the option list still shows all methods — the preference only affects **sort order and the pre-highlighted default**, never elimination of user choice.

**Conflict resolution:** conflicts are resolved via a **fixed priority order set by the user at signup** (e.g., ranking "no printer access" above "fastest return"), rather than a hardcoded system-wide rule. The user can revisit and reorder this priority at any time after signup; it is not locked in permanently. This priority order is **stored client-side only** — in `localStorage` or a synced browser-extension storage API — so the server remains stateless per the Stateless Server Architecture invariant (§1). No preferences table or per-user record is introduced server-side.

---

## 3. End-to-End Pipeline Architecture

```text
[Retailer Order Status Page]
       │ (User clicks extension icon → "Return Order?" prompt)
       ▼
 1. TRIGGER & DOM CAPTURE
       │ ➔ MutationObserver waits for order subtree render
       ▼
 2. ORDER NORMALIZATION (Bedrock Structured Extraction)
       │ ➔ Items, Prices, Delivered Dates → Pydantic models
       │ ➔ (optional) AI pre-picks a common return reason per item
       ▼
 3. POLICY PARSING & DASHBOARD DISPLAY
       │ ➔ Rules / Deadlines / Fees resolved (live fetch if missing from DOM)
       │ ➔ Surfaced on dashboard for user visibility
       ▼
 4. PREFERENCE-WEIGHTED RANKING
       │ ➔ Return methods scored against User Preferences
       │ ➔ Reason defaulted if user leaves it blank
       ▼
 5. PRE-FILL RETURN FORM (Strands WebMCP Navigation)
       │ ➔ Selectors first, fallback to vision/DOM reasoning
       │ ➔ Halts at Method/Fee selection (Human-in-the-loop)
       ▼
 6. USER RE-CHECK RETURN FORM
       │ ├─ Confirm → proceed to Stage 7
       │ └─ Change option → SESSION CONTINUITY LOOP
       │        (context persisted in localStorage; re-fill auto or manual)
       ▼
 7. REVERSE-LOGISTICS BROKERAGE
       │ ➔ [P1] QR Drop-off (no external carrier call)
       │ ➔ [P2] Carrier pickup: user picks carrier first, AI handles info-gathering + label/QR generation
       ▼
 8. [P2] CALENDAR REMINDER HANDOFF
       │ ➔ OAuth-free Google Calendar template URL
       ▼
[End of Flow — User Summary]
```

---

## 4. Detailed Pipeline Stages

### Stage 1: Trigger & DOM Capture
- **Trigger Mechanism:** Flow begins when the user clicks the extension icon while on a retailer order status page, which surfaces a **"Return Order?"** prompt. This click is the explicit user action satisfying Decision D1 — the prompt itself does not appear ambiently on page load.
- **DOM Capture:** After the user confirms the prompt, the content script uses a `MutationObserver` to wait for the SPA to render the order-list subtree, clones only that retailer-specific subtree, and removes scripts, styles, event handlers, and unrelated page content. It must not read at document idle due to SPA render flakiness.
- **API Handoff and Retention:** The service worker sends the sanitized subtree as the context in one `POST /orders/ingest` request. FastAPI passes that request body to Bedrock and returns the structured extraction in the same response; it writes neither the DOM nor model context to Redis, a cache, or a database. The extension retains only the returned structured order and in-progress selections in extension storage for later stages.

### Stage 2: Order Normalization & Reason Pre-Pick
- **Model Invocation:** FastAPI forwards the DOM payload to Claude 3.5 Sonnet via Amazon Bedrock.
- **Latency Boundary:** `POST /orders/ingest` is a synchronous Lambda Function URL request, not an API Gateway long-running workflow. Its single Bedrock parse call has a configurable 9-second deadline, leaving time for request validation and network overhead well below the Lambda timeout. If that deadline is exceeded, the server returns `upstream-unavailable`; it does not queue, persist, or continue the work after the response. The extension may retry this read-only request with backoff while the user is present.
- **Structured Extraction:** Output is forced into typed Pydantic models — `ExtractedItem` (items, prices, delivered dates) and `ReturnPolicy`.
- **Urgency Ranking:** Orders are sorted by remaining return window.
- **Reason Pre-Pick (optional):** The AI proposes a common return reason for the item category (e.g., "doesn't fit," "changed mind," "damaged") based on the product type. This is a suggestion only — the user can accept, edit, or clear it in the review step.

### Stage 3: Policy Parsing & Dashboard Display
- **Policy Fallback:** If the exact return window or restocking fee is missing from the raw DOM, the Strands SDK executes a background tool call to fetch the merchant's live policy page.
- **Dashboard Surfacing:** Rules, deadlines, and fees are displayed on a dashboard view so the user can see policy context before any form is pre-filled — this is distinct from the final return-form review screen.

### Stage 4: Preference-Weighted Ranking
- **Scoring:** Each available return method is scored against the user's active preference(s) — cost, speed, sustainability, or printer access (see [§2](#2-user-preferences-model)).
- **Default Reason:** If the user has not provided or accepted a return reason by this point, the system defaults to a reason along the lines of **"changed my mind"** or **"not suitable"** — whichever most closely matches the closest available option in the retailer's own return-reason form, since exact wording and available options vary by retailer.
- **Pre-Selection Only:** Ranking determines which option is highlighted/pre-selected in the next stage — it does not remove or hide other valid options.

### Stage 5: Pre-Fill Return Form (Human-in-the-Loop Gate)
- **WebMCP Actuation:** The Strands Agent uses WebMCP to navigate the retailer's return flow inside the user's active tab.
- **Deterministic Selectors First:** Documented, hardcoded CSS selectors (e.g., `<button class="return-btn">`) are attempted before falling back to vision/DOM reasoning.
- **Price Evaluation Gate:** Automation pauses once all return methods and prices (e.g., a $7.50 label deduction) are exposed.
- **No Auto-Escalation:** The agent never auto-selects a paid method without explicit confirmation; free QR drop-off is never silently bypassed.

### Stage 6: User Re-Check & Session Continuity Loop
- **Review:** The user reviews the pre-filled return form (item, reason, chosen method) before submission.
- **Edit Path:** If the user wants to change the return option, they pick a new option in the extension. The in-progress context (item, reason, prior selections) is persisted in `localStorage` so it survives the round-trip.
- **Re-fill Behavior:** The extension auto-fills the new selection when the change is a **return method change** (e.g., switching from QR drop-off to printed-label pickup). Changes to **reason or quantity** are completed **manually** by the user rather than auto-filled, since these are user-specific judgment calls the system shouldn't guess at.

### Stage 7: Reverse-Logistics Brokerage
- **[P1] QR Drop-off Path:** If a free in-store or partner QR drop-off is chosen, the flow completes here with no external carrier call.
- **[P2] Printed Label + Carrier Pickup Path:** If the user opts for doorstep pickup:
  1. **Carrier selection (first step):** the user picks which carrier to use — from the available third-party options for the given retailer/order (e.g., USPS, UPS, FedEx). **USPS is not the default or the only option**; all eligible carriers are surfaced and the user chooses explicitly before anything else happens.
  2. **AI-driven info gathering & label generation:** once a carrier is chosen, the Strands Agent handles the rest generically — confirming printer capability and fee acceptance, gathering the address and pickup details needed, checking eligibility, and generating the printable label/QR code for that carrier's pickup flow. This is **not** implemented as a separate hardcoded tool per carrier (e.g., no dedicated `schedule_usps_pickup`-style function); instead the agent navigates the chosen carrier's own pickup flow (via WebMCP, same pattern as Stage 5) and adapts to whichever carrier was selected.
  3. **Scheduling:** the agent completes the booking directly within that carrier's flow, targeting the next available delivery day for collection.
- **Scope confirmed:** this multi-carrier flow stays in scope for the current build phase, using one generic AI-driven process rather than per-carrier integrations.

### Stage 8: Calendar Reminder Handoff [P2]
- **OAuth-Free Event Creation:** The extension opens a prefilled Google Calendar template URL (`action=TEMPLATE`) via `chrome.tabs.create`.
- **Zero Credential Storage:** Requires zero Google account scopes; no Google user data is stored server-side.
- **Reviewable Blocks:** The calendar tab renders the pickup reminder in the user's local timezone, letting them review and save a 15-minute reminder without the extension scraping existing calendar availability.

---

## 5. Decisions Recorded

- Preferences determine ordering and pre-selection only; the user still chooses the return method.
- The extension may suggest a return reason, but the user can edit or clear it.
- Method changes may be re-filled; reason and quantity changes remain user-entered.
- Carrier pickup is multi-carrier: the user selects a carrier, then the agent navigates that carrier's flow.
- The pipeline uses generic browser navigation rather than a dedicated tool per carrier.
