/**
 * The MV3 manifest, kept in its own module so `extension/tests/manifest.test.ts`
 * can assert the permission posture against the same object `wxt.config.ts`
 * ships. A manifest inlined into the WXT config could only be checked by
 * building and reading `.output/`, which is a slower and looser guarantee.
 */

/**
 * The one origin the extension will talk to.
 *
 * `externally_connectable.matches` accepts concrete host patterns only — a bare
 * host wildcard is rejected when the manifest loads — so this hostname is baked
 * into a reviewed artifact and cannot change without a store re-review. The
 * production value is not chosen yet.
 *
 * dev-note: D28 is only partially retained. The dashboard now reads database
 * APIs rather than extension-local summaries, and the dashboard-to-extension
 * binding, transport and revocation are open under ARCH-B6. This entry reserves
 * the channel with the development origin; it is not a settled contract, and
 * ARCH-B6 may replace it outright.
 */
export const DASHBOARD_ORIGIN = process.env.BOOMERANG_DASHBOARD_ORIGIN ?? 'http://localhost:3000'

/** Requested later, in context, once the user has seen a scan work. */
export const RETAILER_ORIGINS: string[] = []

const LOCAL_ORIGIN_PATTERN = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/

/**
 * Fails the build rather than shipping a release that phones home to localhost.
 *
 * Gated on an explicit release flag rather than on WXT's `mode`, because `wxt
 * build` runs in production mode for ordinary local testing — checking `mode`
 * would block every build. `bun run zip`, the command that produces the
 * uploadable artifact, sets the flag.
 */
export function assertReleaseOrigin(origin: string, isRelease: boolean): void {
  if (isRelease && LOCAL_ORIGIN_PATTERN.test(origin)) {
    throw new Error(
      `BOOMERANG_DASHBOARD_ORIGIN is still ${origin}. A release build needs the concrete ` +
        `production dashboard origin — externally_connectable cannot be changed after review ` +
        `without a re-review.`,
    )
  }
}

export const IS_RELEASE = process.env.BOOMERANG_RELEASE === '1'

export function buildManifest(isRelease = IS_RELEASE) {
  assertReleaseOrigin(DASHBOARD_ORIGIN, isRelease)

  return {
    name: 'Boomerang — Returns Concierge',
    description: 'Counts down every return window and drives the return for you.',

    /* Rule 8: nothing else at install. `activeTab` grants access only on a user
       gesture, so the first run cannot inject on page load — the popup offers
       "Scan this page", and the standing host permission for that retailer is
       requested afterwards, in context. Adding <all_urls> to make the first run
       easier trades the product's entire review posture for a convenience. */
    permissions: ['activeTab', 'scripting', 'storage'],

    /* Empty until ARCH-B7 picks the first retailer. Optional, never required:
       these are requested at runtime, after the user has seen a scan work. */
    optional_host_permissions: RETAILER_ORIGINS,

    /* No remote script. The model never returns code — it returns a proposal
       from a closed action vocabulary that trusted extension code validates
       against the live DOM before anything executes. */
    content_security_policy: {
      extension_pages: "script-src 'self'; object-src 'self'",
    },

    /* Chrome requires the path wildcard; the host must stay concrete. */
    externally_connectable: {
      matches: [`${DASHBOARD_ORIGIN}/*`],
    },

    /* dev-note: no `key` yet. Pinning the extension keypair, so the ID is
       stable across builds and `externally_connectable` has a fixed counterpart,
       is separate work that edits this file. Its absence is sequencing, not an
       oversight. */
  }
}
