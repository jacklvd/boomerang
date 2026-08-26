<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

---

# client/AGENTS.md

Next.js app. Read [`../AGENTS.md`](../AGENTS.md) first for repo-wide rules.

**The block above is generated and re-added by `next dev`.** Don't delete it — removing it from a
diff only recreates the uncommitted change. Commit it with your work. Everything below is ours.

## Scope

Three surfaces, in order of importance to the PoC:

1. **Landing page** — what Boomerang is, and the install funnel. This is the whole onboarding
   flow: `landing → subscribe email → install extension`. There is no signup, no OAuth, no
   account creation, because there is no Google grant to obtain (D1/D2 in
   [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)).
2. **Order dashboard** — the same ranked order list the extension popup shows, on a bigger canvas.
3. **Nothing else.** No admin, no settings that duplicate extension state.

**The client is a read-only view over the server API.** It never touches retailer page data, never
holds a credential, never calls a carrier. If a feature needs page access, it belongs in the
extension; if it needs a credential, it belongs on the server.

## Phase

| Phase | State |
|---|---|
| **Now** | Next.js starter page. `app/page.tsx` is untouched scaffolding. |
| **Phase 1** | Landing page + install funnel. Buildable immediately — nothing blocks it. |
| **Phase 2** | Order dashboard. Depends on `GET /orders` existing on the server, so don't start it first. |

The dashboard is deliberately *not* phase 1: the extension popup is the primary surface, and a
dashboard with no data behind it is a mock, not a milestone.

## Commands

```bash
bun install
bun dev            # :3000
bun run lint       # eslint
bun run format     # prettier
```

`bun` is pinned via `packageManager`. Don't introduce `npm` or `yarn` lockfiles.

Husky + lint-staged run eslint and prettier on commit. If the pre-commit hook fails, fix the code
— don't `--no-verify`.

## Conventions

- **This is Next.js 16** with breaking changes from what you may remember. Read the relevant guide
  in `node_modules/next/dist/docs/` before writing app-router code. Heed deprecation notices.
- **UI stack:** shadcn-ui over Base UI, Tailwind 4, Phosphor icons, `tw-animate-css`. Compose from
  `components/ui/`; add primitives with the shadcn CLI rather than hand-rolling.
- **`cn()` from `lib/utils.ts`** for conditional classes — `clsx` + `tailwind-merge`. Don't
  string-concatenate class names.
- **`prettier-plugin-tailwindcss` sorts class order.** Don't fight it manually.
- **Server URL comes from `NEXT_PUBLIC_API_URL`** (`http://localhost:8000` in compose). Never
  hardcode a host.

## Rules specific to this workspace

- **No user order data in the Next.js app's own storage.** The dashboard renders what the server
  returns for the current install token; it doesn't cache order contents to localStorage.
- **The landing page makes the compliance promise.** Whatever it says about what leaves the
  browser has to match the extension's Chrome Web Store disclosure exactly — a reviewer will read
  both. Coordinate copy changes with the listing.
- **Copy rules carry here too.** Never promise a pickup window; "with tomorrow's mail delivery."
  Never imply Boomerang reads your email — it doesn't, and that's a selling point worth stating
  plainly rather than a limitation to hide.
- **Install funnel targets Chrome Web Store only.** There is no second distribution channel.

## Gotchas

- **`prepare` runs `cd .. && husky client/.husky`** — the hook directory is nested but git's hook
  path points at the repo root. If hooks stop firing after a fresh clone, re-run `bun install`.
- **`sharp` and `unrs-resolver` are in `ignoreScripts` and `trustedDependencies`.** If image
  optimization misbehaves on a new machine, that's the first place to look.
- **The client is not the demo.** During the PoC, the extension popup carries the story; don't
  over-invest in dashboard polish before the return flow works end to end.
