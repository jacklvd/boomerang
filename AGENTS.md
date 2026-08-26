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
| `infra/` | VPC + EC2 + Terraform | scaffolded, never applied; not PoC-critical | [`infra/AGENTS.md`](infra/AGENTS.md) |
| `docs/` | Product sketch, architecture decisions, narrative proposals | — | [`docs/SKETCH.md`](docs/SKETCH.md) |
| `.claude/` | Claude Code settings, raw research artifacts, tickets | — | — |

```bash
docker compose up --build     # client :3000, server :8000
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
   address-specific and a meaningful share of users get a no. Persist `confirmationNumber` and
   `ETag` **together** — without the ETag nobody can cancel.

4. **The box needs a printed label, not just a QR code.** (D6) Free USPS pickup only covers
   packages with prepaid postage affixed. A flow that stops at a QR code produces an illegitimate
   pickup.

5. **Never promise a pickup time window.** (D6) Free Carrier Pickup happens on the normal delivery
   round. Say "with tomorrow's mail delivery." The two-hour window is a different, paid product.

6. **Never silently escalate to a paid option.** If USPS is ineligible, offer drop-off or a priced
   alternative with the price stated.

7. **The server only ever sees what the extension sends it.** There is no background job reaching
   into user data — there's no credential that would let one work. If you're writing one, you've
   misread the architecture.

## Cross-cutting conventions

- **Comments.** The codebase uses `# dev-note:` / `// dev-note:` for decisions a reader would
  otherwise re-litigate. Explain *why*, not *what*.
- **Secrets.** `.env` is gitignored, `.env.example` is not. Carrier and retailer credentials live
  server-side only — the extension must never hold one.
- **Branching.** Branch from `main`; don't commit to it directly.
- **Docs.** When a doc and the code disagree, the doc is stale — fix it in the same PR.
- **Scope.** The PoC target is one retailer end to end, not two retailers halfway.
