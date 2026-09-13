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

  it('reports a closed tab as unavailable instead of returning a dead handle', async () => {
    const { tabs, tab } = await withTab('https://nordstrom.com/orders')
    await tabs.remove(tab.id)
    expect(await readActiveTab(tabs)).toEqual({ kind: 'unavailable' })
  })
})

describe('scanActivePage', () => {
  it('returns what the injected probe reported', async () => {
    const scripting = new FakeChromeScripting()
    scripting.stage(1, { rowCount: 6 })
    expect(await scanActivePage(scripting, 1)).toEqual({ rowCount: 6 })
  })

  it('distinguishes a page that refused from a page with no orders', async () => {
    const scripting = new FakeChromeScripting()
    scripting.stage(1, undefined)
    await expect(scanActivePage(scripting, 1)).rejects.toThrow('did not answer')

    scripting.stage(2, { rowCount: 0 })
    expect(await scanActivePage(scripting, 2)).toEqual({ rowCount: 0 })
  })

  it('fails loudly when nothing was staged, rather than reading an empty page', async () => {
    await expect(scanActivePage(new FakeChromeScripting(), 1)).rejects.toThrow('No DOM staged')
  })
})
