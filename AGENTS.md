# AGENTS.md

Repo-wide orientation. Each workspace has its own `AGENTS.md` with local scope, phase, and
conventions — read this one first, then the one for the directory you're working in.

## What Boomerang is

A returns concierge. A browser extension reads retailer order pages the user visits, a FastAPI
service parses them with Bedrock and ranks return-window urgency, and the agent drives the return
to a printed label, books a free USPS pickup, and writes a calendar reminder.

Start with [`docs/SKETCH.md`](docs/SKETCH.md) for the product and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the shape and the decisions behind it.

## Map

| Path | Scope | Phase | Guide |
|---|---|---|---|
| `extension/` | Reads order pages, drives return flows, opens the calendar tab | **not built** — arrives with its own `AGENTS.md` | — |
| `client/` | Landing page, install funnel, order dashboard | scaffolded; dashboard is phase 2 | [`client/AGENTS.md`](client/AGENTS.md) |
| `server/` | Parsing, ranking, carrier broker, credential holder | `/health` only; ingestion is phase 1 | [`server/AGENTS.md`](server/AGENTS.md) |
| `infra/` | Lambda + Function URL + SSM + CloudWatch, in Terraform | EC2 scaffold superseded, never applied; not PoC-critical | [`infra/AGENTS.md`](infra/AGENTS.md) |
| `docs/` | Product sketch, architecture decisions, narrative proposals | — | [`docs/SKETCH.md`](docs/SKETCH.md) |
| `design/` | Requirements and high-level design — the current spec | — | [`design/boomerang-requirements.md`](design/boomerang-requirements.md) |
| `.claude/` | Claude Code settings, raw research artifacts, tickets | — | — |

```bash
docker compose up --build     # client :3000, server :8000
./scripts/setup-hooks.sh      # once per clone — installs the repo-wide pre-commit hook
```

## The rules that aren't style preferences

These come out of research (`.claude/artifacts/`) and violating them breaks the product, not just
consistency. Decision IDs refer to `docs/ARCHITECTURE.md`.

1. **No Google OAuth scopes. Ever, in the PoC.** (D1, D2) The whole architecture exists to avoid
   the restricted-scope regime — verification, CASA, ~$540–$1,800/yr, 6–12 week lead time. One
   Gmail or Calendar scope forfeits all of it. If a task seems to need one, the answer is a
   different design.

2. **No Gmail, in any form.** Not the API, not scraping. Order data comes from retailer pages.

3. **Never schedule a pickup without a successful eligibility check first.** (D5) Eligibility is
   address-specific and a meaningful share of users get a no. Store the `confirmationNumber` and
   the address it was booked against; **never store the `ETag`** — it is good for one hour or one
   use, so a later cancellation refreshes the pickup to get a current one, then cancels.

4. **Free USPS pickup requires prepaid USPS postage on the box.** (D6) Two things follow, and
   both are easy to get wrong in opposite directions. A QR code alone is not a pickup — but it is
   not a failure either: retailer free QR drop-off is a legitimate, successful outcome that simply
   skips the pickup step. And a *printed* label is not sufficient on its own — if the postage on it
   is UPS or FedEx, a USPS carrier will not collect it, because the carrier is collecting mail.
   Record which carrier's postage is on the box and gate scheduling on that, not on "a label
   exists."

5. **Never promise a pickup time window, and never assume the day.** (D6) Free Carrier Pickup
   happens on the normal delivery round, so it is a day, not a window. Name the day USPS returned
   in its own response — usually tomorrow, but today for a request before the 2 AM Central cutoff,
   and Monday on a Saturday evening. The two-hour window is a different, paid product.

6. **Never silently escalate to a paid option, and never pick the return method for the user.**
   Where the retailer offers a choice of return methods, stop and present every one of them with
   its price. Buying a paid printable label out of the user's refund to satisfy our own pickup
   precondition is the exact failure this rule exists to prevent. If USPS is ineligible, offer
   drop-off or a priced alternative with the price stated.

7. **The server only ever sees what the extension sends it.** There is no background job reaching
   into user data — there's no credential that would let one work. If you're writing one, you've
   misread the architecture.

8. **The manifest declares `activeTab`, `scripting` and `storage` — nothing else at install.**
   `activeTab` grants access only on a user gesture, so the first run *cannot* inject on page load:
   the popup offers "Scan this page", and the standing host permission for that retailer is
   requested afterwards, in context, once the user has seen it work. Adding `<all_urls>` to "make
   the first run work" trades the product's entire review posture for a convenience.

9. **The model drives the return flow through a closed action vocabulary.** `click`,
   `select_option`, `fill`, `pause_for_user`, `report_stuck` — forced tool choice, so there is no
   path where attacker-influenced retailer DOM talks the model into an action outside that list.
   `fill` never targets a password, payment or file-upload input. Selectors are tried first; the
   model is asked only when they miss.

## Cross-cutting conventions

- **Comments.** The codebase uses `# dev-note:` / `// dev-note:` for decisions a reader would
  otherwise re-litigate. Explain *why*, not *what*.
- **Secrets.** `.env` is gitignored, `.env.example` is not. Carrier and retailer credentials live
  server-side only — the extension must never hold one.
- **Branching.** Branch from `main`; don't commit to it directly.
- **Hooks are repo-wide, in `/.husky/`.** Git allows exactly one `core.hooksPath`, so there is
  one dispatcher for the whole repo; it gates each workspace's checks on whether that workspace
  has staged files. Don't add a second hooks directory under a workspace — it will be silently
  ignored. Per-workspace commands live in that workspace's `AGENTS.md`
  (`make -C server check`, `bunx lint-staged` in `client/`).
- **Docs.** When a doc and the code disagree, the doc is stale — fix it in the same PR.
- **Scope.** The PoC target is one retailer end to end, not two retailers halfway.
