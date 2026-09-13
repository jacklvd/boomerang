/**
 * Whether a URL looks like a page worth scanning — decided from the URL alone.
 *
 * That restriction is the point, not a shortcut. The popup runs this before the
 * user has asked for anything, and reading the DOM to answer it would be
 * exactly the standing access the first screen promises we do not have. A URL
 * is something the browser already handed us.
 *
 * dev-note: a generic path heuristic, not a retailer registry. `RETAILER_ORIGINS`
 * is deliberately empty under D7 and there is no adapter list yet, so anything
 * keyed by retailer would be inventing one. The ceiling is obvious — it matches
 * `/orders` on sites that sell nothing — and the cost of being wrong is a
 * heading, since the user can scan either way.
 */
const ORDER_PATH =
  /(^|\/)(orders?|order-history|order_history|purchases|my-orders|my-account\/orders|returns?)(\/|$)/i

export function looksLikeOrderPage(url: URL): boolean {
  return ORDER_PATH.test(url.pathname)
}

/** What the popup shows instead of the full URL. A path is enough context. */
export function describe(url: URL): string {
  const path = url.pathname === '/' ? '' : url.pathname.replace(/\/$/, '')
  return `${url.hostname.replace(/^www\./, '')}${path}`
}
