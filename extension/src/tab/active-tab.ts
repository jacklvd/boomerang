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
 * What one scan currently reports back.
 *
 * Counts, never content. The extractor that turns a page into normalized orders
 * does not exist yet, and this is not a down payment on it — it is the smallest
 * result that proves the injection actually ran. Nothing here is page text, so
 * nothing here needs the egress guard that the real extraction will.
 */
export type PageProbe = {
  rowCount: number
}

/* Serialized and run in the page, so it closes over nothing and calls nothing
   from this module. dev-note: a structural guess with an obvious ceiling — it
   counts elements that name themselves, and a retailer whose markup does not
   will report zero. The adapter that knows better replaces it. */
function countOrderRows(): { rowCount: number } {
  const selectors = '[class*="order" i], [data-testid*="order" i], [id*="order" i]'
  return { rowCount: document.querySelectorAll(selectors).length }
}

export async function scanActivePage(
  scripting: ScriptingArea,
  tabId: number,
): Promise<PageProbe> {
  const [injection] = await scripting.executeScript({
    target: { tabId },
    func: countOrderRows,
  })

  /* An injection that returns nothing is a page that refused us — a
     navigation mid-scan, or a frame Chrome declined to enter. Reporting zero
     rows would be indistinguishable from an empty order list. */
  if (!injection || injection.result === undefined || injection.result === null) {
    throw new Error('the page did not answer the scan')
  }
  return injection.result
}
