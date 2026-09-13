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

1. **Order dashboard** — the product home (D8 in
   [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)). It reads normalized orders, deadlines,
   values and return state **from the server**, scoped to the signed-in account. It degrades to an
   install prompt when the extension isn't connected, because the extension is still the only thing
   that can read a retailer page.
2. **Landing page** — what Boomerang is, and the install funnel:
   `landing → sign in with Google → install extension`. Google is the v1 account provider and the
   backend keys users by the OIDC `sub` (D10).
3. **Privacy page** — the disclosure the Chrome Web Store listing points at.
4. **Nothing else.** No admin, no settings that duplicate extension state.

**The client never touches retailer page data, never holds a retailer credential, and never calls a
carrier.** If a feature needs page access it belongs in the extension; if it needs a credential it
belongs on the server. Durable account state is the server's; the detailed workflow state of an
in-progress return is the extension's, and is never uploaded (D9).

## Phase

| Phase     | State                                                                                                                              |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Now**   | Landing, privacy and dashboard pages are built and rendering fixtures from `lib/orders.ts`.                                        |
| **Next**  | Google sign-in, then swapping the fixture for `GET /orders`. Both need server endpoints that don't exist yet.                      |
| **After** | Extension connectivity over `externally_connectable`, which drives the connected/disconnected state the dashboard already renders. |

`lib/orders.ts` is the single fixture behind every surface. When the API lands it gets deleted, not
extended — don't grow it into a mock backend.

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
- **Rendering mode is unresolved.** This file has long said static export (`output: "export"`)
  while `next.config.ts` says `output: "standalone"`. D8 makes the dashboard read authenticated
  server data, which a pure static export can't do on its own. Settle this before the auth PR;
  until then, don't add route handlers or middleware on the assumption either answer won.

## Rules specific to this workspace

- **No user order data in the Next.js app's own storage.** The dashboard renders what the server
  returns for the signed-in account; it doesn't cache order contents to localStorage.
- **The landing page makes the compliance promise.** Whatever it says about what leaves the
  browser has to match the extension's Chrome Web Store disclosure exactly — a reviewer will read
  both. Coordinate copy changes with the listing.
- **Copy rules carry here too.** Never promise a pickup window, and never write "tomorrow" — name
  the day USPS actually returned. Never imply Boomerang reads your email — it doesn't, and that's a
  selling point worth stating plainly rather than a limitation to hide.
- **Install funnel targets Chrome Web Store only.** There is no second distribution channel.
- **The dashboard lives on one fixed, known origin, and that origin is a shipped constant.**
  `externally_connectable.matches` in the extension manifest accepts **concrete host patterns
  only** — a bare wildcard is rejected when the manifest loads — so the hostname is baked into a
  reviewed artifact and can't be changed without a store re-review. Preview and branch deploy URLs
  are not addressable by the extension; test the dashboard against the real origin.
  **The production hostname is not chosen yet** — see open question 1 in
  [`../design/boomerang-high-level-design.md`](../design/boomerang-high-level-design.md) §11. It
  blocks the extension manifest, not the landing page.

## Gotchas

- **`prepare` runs `cd .. && husky client/.husky`** — the hook directory is nested but git's hook
  path points at the repo root. If hooks stop firing after a fresh clone, re-run `bun install`.
- **`sharp` and `unrs-resolver` are in `ignoreScripts` and `trustedDependencies`.** If image
  optimization misbehaves on a new machine, that's the first place to look.
- **The client is not the demo.** During the PoC, the extension popup carries the story; don't
  over-invest in dashboard polish before the return flow works end to end.
