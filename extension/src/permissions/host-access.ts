/**
 * The second tier of the permission model: a standing host permission for one
 * retailer, offered only after the user has seen a scan work.
 *
 * D7 sets the shape. The extension installs with `activeTab`, which grants one
 * tab for one gesture and nothing on page load. A standing permission removes
 * the tap — and is requested "only after a user gesture and in context", never
 * at install, and never as `<all_urls>`.
 *
 * Surfaces are injected rather than reached for, so the same code runs against
 * `browser.permissions` and against the fake.
 */
import { RETAILER_ORIGINS } from '@/manifest.config'

export type PermissionsArea = {
  contains(permissions: { origins: string[] }): Promise<boolean>
  request(permissions: { origins: string[] }): Promise<boolean>
  remove(permissions: { origins: string[] }): Promise<boolean>
}

/**
 * The match pattern for one origin — `https://www.example.com/*`.
 *
 * Exactly the origin the user is looking at, not a registrable-domain wildcard
 * like `https://*.example.com/*`. The narrower pattern is occasionally less
 * useful, because a retailer that moves the user between `example.com` and
 * `shop.example.com` will ask again on the second host. That is the correct
 * trade: the screen offering this says "this one site only", and a wildcard
 * would quietly cover hosts the user was never shown.
 */
export function patternFor(origin: string): string {
  return `${origin}/*`
}

/** `https://www.example.com/*` → a test for one origin. */
function matches(pattern: string, origin: string): boolean {
  const withoutPath = pattern.replace(/\/\*$/, '')
  if (!withoutPath.includes('*')) return withoutPath === origin

  /* Only a leading host wildcard is meaningful here, and it must match on a
     dot boundary: `*.example.com` must cover `www.example.com` and
     `example.com`, and must not cover `evilexample.com`. */
  const escaped = withoutPath
    .replace(/[.+?^${}()|[\]\\]/g, '\\$&')
    .replace('*\\.', '(?:[^/]+\\.)?')
  if (escaped.includes('*')) return false
  return new RegExp(`^${escaped}$`).test(origin)
}

/**
 * Whether this origin is one the extension is allowed to ask about at all.
 *
 * Chrome refuses a `request()` for an origin the manifest never declared under
 * `optional_host_permissions`, so asking anyway would put a button on screen
 * that cannot work. `RETAILER_ORIGINS` is deliberately empty today, which means
 * the offer is never made — the correct behaviour, not a missing feature.
 *
 * dev-note: populating that list is a product decision about which retailers
 * are supported, and it gates this whole screen. Until an adapter list exists
 * there is nothing to put in it.
 */
export function isOfferable(origin: string): boolean {
  return RETAILER_ORIGINS.some((pattern) => matches(pattern, origin))
}

export async function hasStandingAccess(
  permissions: PermissionsArea,
  origin: string,
): Promise<boolean> {
  return permissions.contains({ origins: [patternFor(origin)] })
}

export type AccessResult = 'granted' | 'denied' | 'not-offerable' | 'no-gesture'

/**
 * Asks for the standing permission. **Call this only from an event handler.**
 *
 * Chrome rejects `request()` outside a user gesture, and that rejection is the
 * mechanism D7 relies on: the extension cannot quietly acquire standing access
 * on a timer or on page load even if some later code tries. `no-gesture` is
 * reported rather than swallowed, because it means a caller broke that rule and
 * the user saw nothing at all.
 */
export async function requestStandingAccess(
  permissions: PermissionsArea,
  origin: string,
): Promise<AccessResult> {
  if (!isOfferable(origin)) return 'not-offerable'

  try {
    return (await permissions.request({ origins: [patternFor(origin)] })) ? 'granted' : 'denied'
  } catch (error) {
    /* The real API rejects with "This function must be called during a user
       gesture". A denial resolves false instead — the two are different facts
       and must not collapse into one. */
    if (error instanceof Error && /user gesture/i.test(error.message)) return 'no-gesture'
    throw error
  }
}

export async function revokeStandingAccess(
  permissions: PermissionsArea,
  origin: string,
): Promise<boolean> {
  return permissions.remove({ origins: [patternFor(origin)] })
}
