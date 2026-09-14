/**
 * Reading the tab the user is looking at, and scanning it when they ask.
 *
 * Both halves depend on `activeTab`, which D7 picks over a host permission.
 * The grant is what makes the first screen's promise true rather than
 * decorative: Chrome hands it over when the user invokes the extension — a
 * toolbar click, a context menu, a shortcut — and it covers only that tab. The
 * extension cannot read this page, or any page, until that happens.
 *
 * Written against injected surfaces rather than the `chrome` global so the
 * fakes can drive it. The popup passes the real ones in.
 */
import { captureOrderSubtree, type Capture } from '@/src/extract/capture'
import { redactionTotal, sanitize, type SanitizeReport } from '@/src/extract/sanitize'
import { describe, looksLikeOrderPage } from './order-page'

export type TabsArea = {
  query(query: { active?: boolean; currentWindow?: boolean }): Promise<
    { id?: number; url?: string }[]
  >
}

export type ScriptingArea = {
  executeScript<T>(injection: {
    target: { tabId: number }
    func: () => T
  }): Promise<{ result: T }[]>
}

export type ActiveTab =
  /** No tab, or one Chrome will not describe to us. */
  | { kind: 'unavailable' }
  /** A real page we are not allowed to touch, whatever the user asks. */
  | { kind: 'blocked'; label: string }
  | {
      kind: 'ready'
      tabId: number
      url: string
      /** `nordstrom.com/orders` — what the site chip shows. */
      label: string
      looksLikeOrders: boolean
    }

/**
 * Chrome will not inject into its own pages, the Web Store, or another
 * extension, and `activeTab` does not change that. Deciding it here means the
 * popup never offers a button that cannot work.
 */
const INJECTABLE_PROTOCOLS = new Set(['http:', 'https:'])

export async function readActiveTab(tabs: TabsArea): Promise<ActiveTab> {
  const [tab] = await tabs.query({ active: true, currentWindow: true })

  /* A missing `url` is the ordinary shape of "not granted yet", not an error:
     without activeTab or a host permission Chrome returns the tab with the URL
     stripped. Treating it as unavailable is the honest reading. */
  if (!tab || tab.id === undefined || !tab.url) return { kind: 'unavailable' }

  let url: URL
  try {
    url = new URL(tab.url)
  } catch {
    return { kind: 'unavailable' }
  }

  if (!INJECTABLE_PROTOCOLS.has(url.protocol)) {
    return { kind: 'blocked', label: describe(url) }
  }

  return {
    kind: 'ready',
    tabId: tab.id,
    url: tab.url,
    label: describe(url),
    looksLikeOrders: looksLikeOrderPage(url),
  }
}

/**
 * What one scan produced.
 *
 * The sanitized tree itself is deliberately not here. Nothing may send it yet —
 * the ingestion endpoint is a deferred contract — and holding it on a result
 * object invites some future caller to log it or stash it, which the zero
 * durable retention rule forbids. The caller that eventually posts it will take
 * it straight from `sanitize()`.
 */
export type ScanResult = {
  /** Elements captured, after the excluded tags were dropped. */
  nodeCount: number
  /** A cap stopped the walk, so the tree is partial. */
  truncated: boolean
  /** What the egress guard removed, by kind. */
  redactions: SanitizeReport['redactions']
  redactionCount: number
}

export async function scanActivePage(
  scripting: ScriptingArea,
  tabId: number,
): Promise<ScanResult> {
  const [injection] = await scripting.executeScript({
    target: { tabId },
    func: captureOrderSubtree,
  })

  /* An injection that returns nothing is a page that refused us — a navigation
     mid-scan, or a frame Chrome declined to enter. Reporting an empty capture
     would be indistinguishable from an empty page. */
  if (!injection || injection.result === undefined || injection.result === null) {
    throw new Error('the page did not answer the scan')
  }

  /* Sanitize immediately, in the same expression that receives the capture.
     The raw tree must not outlive this line: every later step works from the
     guarded version, so there is no path on which an unguarded one is handy. */
  const { report } = sanitize(injection.result as Capture)

  return {
    nodeCount: report.nodeCount,
    truncated: report.truncated,
    redactions: report.redactions,
    redactionCount: redactionTotal(report),
  }
}
