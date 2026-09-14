import { describe, expect, it } from 'vitest'

import { FakeChromeScripting } from './fakes/chrome-scripting'
import { FakeChromeTabs } from './fakes/chrome-tabs'
import { readActiveTab, scanActivePage } from '../src/tab/active-tab'
import { describe as describeUrl, looksLikeOrderPage } from '../src/tab/order-page'

const at = (url: string) => new URL(url)

describe('looksLikeOrderPage', () => {
  it('recognises the usual order-page paths', () => {
    for (const url of [
      'https://nordstrom.com/orders',
      'https://shop.example/my-account/orders',
      'https://shop.example/order-history',
      'https://shop.example/purchases/',
      'https://shop.example/account/order/1001',
    ]) {
      expect(looksLikeOrderPage(at(url)), url).toBe(true)
    }
  })

  it('does not fire on a page that merely mentions orders', () => {
    for (const url of [
      'https://nordstrom.com/',
      'https://shop.example/products/reorder-pad',
      'https://shop.example/help/ordering',
      'https://shop.example/search?q=orders',
    ]) {
      expect(looksLikeOrderPage(at(url)), url).toBe(false)
    }
  })

  it('shows host and path, without the www or a trailing slash', () => {
    expect(describeUrl(at('https://www.nordstrom.com/orders/'))).toBe('nordstrom.com/orders')
    expect(describeUrl(at('https://nordstrom.com/'))).toBe('nordstrom.com')
  })
})

describe('readActiveTab', () => {
  const withTab = async (url: string) => {
    const tabs = new FakeChromeTabs()
    const tab = await tabs.create({ url })
    tabs.activate(tab.id)
    return { tabs, tab }
  }

  it('reports the active tab and whether it looks like orders', async () => {
    const { tabs, tab } = await withTab('https://www.nordstrom.com/orders')
    expect(await readActiveTab(tabs)).toEqual({
      kind: 'ready',
      tabId: tab.id,
      url: 'https://www.nordstrom.com/orders',
      label: 'nordstrom.com/orders',
      looksLikeOrders: true,
    })
  })

  it('still offers a page it does not recognise', async () => {
    const { tabs } = await withTab('https://nordstrom.com/')
    expect(await readActiveTab(tabs)).toMatchObject({ kind: 'ready', looksLikeOrders: false })
  })

  it('blocks a page Chrome will not let us inject into', async () => {
    for (const url of ['chrome://extensions', 'about:blank', 'file:///Users/me/orders.html']) {
      const { tabs } = await withTab(url)
      expect((await readActiveTab(tabs)).kind, url).toBe('blocked')
    }
  })

  it('treats a stripped URL as not granted rather than as an error', async () => {
    /* What Chrome actually returns before activeTab: the tab, minus its URL. */
    const tabs = { query: async () => [{ id: 7 }] }
    expect(await readActiveTab(tabs)).toEqual({ kind: 'unavailable' })
  })

  it('survives having no active tab at all', async () => {
    const tabs = new FakeChromeTabs()
    await tabs.create({ url: 'https://nordstrom.com/orders' })
    tabs.deactivate()
    expect(await readActiveTab(tabs)).toEqual({ kind: 'unavailable' })
  })

  /* `tabs.query` itself can reject — "Extension context invalidated" when the
     extension is reloaded while the popup is open, for one. That rejection is
     not caught here: the caller decides, and the popup's answer is the
     unavailable screen rather than a spinner that never resolves. */
  it('lets a rejecting query through rather than swallowing it', async () => {
    const broken = {
      query: async () => {
        throw new Error('Extension context invalidated.')
      },
    }
    await expect(readActiveTab(broken)).rejects.toThrow('Extension context invalidated')
  })

  it('reports a closed tab as unavailable instead of returning a dead handle', async () => {
    const { tabs, tab } = await withTab('https://nordstrom.com/orders')
    await tabs.remove(tab.id)
    expect(await readActiveTab(tabs)).toEqual({ kind: 'unavailable' })
  })
})

describe('scanActivePage', () => {
  const captureOf = (root: unknown, nodeCount = 3, truncated = false) => ({
    root,
    nodeCount,
    truncated,
  })

  it('reports what was captured and what the guard removed', async () => {
    const scripting = new FakeChromeScripting()
    scripting.stage(
      1,
      captureOf({
        tag: 'div',
        attrs: {},
        children: [
          { tag: 'p', attrs: {}, text: 'Wool Overcoat · $180.00' },
          { tag: 'p', attrs: {}, text: 'jack@example.com' },
        ],
      }),
    )

    const result = await scanActivePage(scripting, 1)
    expect(result).toMatchObject({ nodeCount: 3, truncated: false, redactionCount: 1 })
    expect(result.redactions.email).toBe(1)
  })

  it('carries truncation through so a partial tree is never read as a whole one', async () => {
    const scripting = new FakeChromeScripting()
    scripting.stage(1, captureOf({ tag: 'div', attrs: {} }, 1500, true))
    expect(await scanActivePage(scripting, 1)).toMatchObject({ truncated: true })
  })

  /* The guarded tree is not on the result at all — nothing may send it yet,
     and an object carrying it would invite a caller to log or store it. */
  it('returns no page content, only counts', async () => {
    const scripting = new FakeChromeScripting()
    scripting.stage(1, captureOf({ tag: 'p', attrs: {}, text: 'Wool Overcoat' }, 1))
    expect(JSON.stringify(await scanActivePage(scripting, 1))).not.toContain('Wool Overcoat')
  })

  it('distinguishes a page that refused from a page with nothing on it', async () => {
    const scripting = new FakeChromeScripting()
    scripting.stage(1, undefined)
    await expect(scanActivePage(scripting, 1)).rejects.toThrow('did not answer')

    scripting.stage(2, captureOf(null, 0))
    expect(await scanActivePage(scripting, 2)).toMatchObject({ nodeCount: 0 })
  })

  /* `executeScript` types its result `any`. A page-side throw comes back as an
     error object, and a cast would have handed that straight to the guard —
     which would have counted no redactions in a tree it never read. */
  it('refuses an answer that is not a capture at all', async () => {
    for (const answer of [
      { message: 'ReferenceError: x is not defined' },
      'the page returned a string',
      captureOf({ tag: 'div', attrs: {} }, '3' as unknown as number),
      captureOf({ attrs: {} }),
      42,
    ]) {
      /* A fresh double per case: staging repeats its last result rather than
         replacing it, so one shared double would re-read the first answer. */
      const scripting = new FakeChromeScripting()
      scripting.stage(1, answer)
      await expect(scanActivePage(scripting, 1), JSON.stringify(answer)).rejects.toThrow(
        'did not answer',
      )
    }
  })

  it('fails loudly when nothing was staged, rather than reading an empty page', async () => {
    await expect(scanActivePage(new FakeChromeScripting(), 1)).rejects.toThrow('No DOM staged')
  })
})
