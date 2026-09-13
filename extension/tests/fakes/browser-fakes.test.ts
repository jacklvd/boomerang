import { beforeEach, describe, expect, it } from 'vitest'

import { type FakeChrome, installFakeChrome } from './chrome'
import { PermissionGestureError } from './chrome-permissions'

let chrome: FakeChrome

beforeEach(() => {
  chrome = installFakeChrome()
  chrome.reset()
})

describe('tabs', () => {
  it('a closed tab reports not live', async () => {
    const tab = await chrome.tabs.create({ url: 'https://example.test/orders' })
    expect(chrome.tabs.isLive(tab.id)).toBe(true)

    await chrome.tabs.remove(tab.id)
    expect(chrome.tabs.isLive(tab.id)).toBe(false)
  })

  it('notifies onRemoved listeners', async () => {
    const seen: number[] = []
    chrome.tabs.onRemoved.addListener((id) => seen.push(id))

    const tab = await chrome.tabs.create({ url: 'https://example.test/' })
    await chrome.tabs.remove(tab.id)

    expect(seen).toEqual([tab.id])
  })

  it('refuses to drive a closed tab', async () => {
    const tab = await chrome.tabs.create({ url: 'https://example.test/' })
    await chrome.tabs.remove(tab.id)

    await expect(chrome.tabs.update(tab.id, { url: 'https://example.test/next' })).rejects.toThrow(
      /closed/,
    )
  })

  it('lets a test navigate the page under the driver', async () => {
    const tab = await chrome.tabs.create({ url: 'https://example.test/step-1' })
    chrome.tabs.setUrl(tab.id, 'https://example.test/step-2')
    expect((await chrome.tabs.get(tab.id)).url).toBe('https://example.test/step-2')
  })
})

describe('scripting', () => {
  it('returns the DOM the test staged', async () => {
    const tab = await chrome.tabs.create({ url: 'https://example.test/' })
    chrome.scripting.stage(tab.id, '<main>one</main>')

    const [first] = await chrome.scripting.executeScript({ target: { tabId: tab.id } })
    expect(first?.result).toBe('<main>one</main>')
  })

  it('walks successive observations, because the page changes between reads', async () => {
    const tab = await chrome.tabs.create({ url: 'https://example.test/' })
    chrome.scripting.stage(tab.id, '<main>one</main>', '<main>two</main>')

    const read = async () =>
      (await chrome.scripting.executeScript({ target: { tabId: tab.id } }))[0]?.result

    expect(await read()).toBe('<main>one</main>')
    expect(await read()).toBe('<main>two</main>')
    // The last one repeats rather than erroring.
    expect(await read()).toBe('<main>two</main>')
  })

  it('fails loudly when nothing is staged', async () => {
    const tab = await chrome.tabs.create({ url: 'https://example.test/' })
    await expect(chrome.scripting.executeScript({ target: { tabId: tab.id } })).rejects.toThrow(
      /No DOM staged/,
    )
  })
})

describe('permissions', () => {
  const origins = ['https://retailer.test/*']

  it('rejects a request made outside a user gesture', async () => {
    await expect(chrome.permissions.request({ origins })).rejects.toBeInstanceOf(
      PermissionGestureError,
    )
    expect(await chrome.permissions.contains({ origins })).toBe(false)
  })

  it('grants inside a gesture', async () => {
    const granted = await chrome.permissions.duringGesture(() =>
      chrome.permissions.request({ origins }),
    )
    expect(granted).toBe(true)
    expect(await chrome.permissions.contains({ origins })).toBe(true)
  })

  it('honours a denial', async () => {
    chrome.permissions.denyNextRequest()
    const granted = await chrome.permissions.duringGesture(() =>
      chrome.permissions.request({ origins }),
    )
    expect(granted).toBe(false)
    expect(await chrome.permissions.contains({ origins })).toBe(false)
  })

  it('revokes', async () => {
    chrome.permissions.grant(...origins)
    await chrome.permissions.remove({ origins })
    expect(await chrome.permissions.contains({ origins })).toBe(false)
  })

  it('closes the gesture window afterwards', async () => {
    await chrome.permissions.duringGesture(async () => {})
    await expect(chrome.permissions.request({ origins })).rejects.toBeInstanceOf(
      PermissionGestureError,
    )
  })
})

describe('worker lifecycle', () => {
  it('terminate loses memory but not storage', async () => {
    await chrome.storage.local.set({ session: { step: 'choose' } })
    chrome.worker.remember('session', { step: 'choose' })

    chrome.worker.terminate()

    expect(chrome.worker.recall('session')).toBeUndefined()
    expect(await chrome.storage.local.get('session')).toEqual({ session: { step: 'choose' } })
  })

  it('forces rehydration after a death, and only then', async () => {
    await chrome.storage.local.set({ session: { step: 'choose' } })

    const rehydrate = async () => (await chrome.storage.local.get('session')).session

    expect(await chrome.worker.withRehydration('session', rehydrate)).toEqual({ step: 'choose' })
    expect(chrome.worker.rehydrations).toBe(1)

    // Warm memory: no second read.
    await chrome.worker.withRehydration('session', rehydrate)
    expect(chrome.worker.rehydrations).toBe(1)

    chrome.worker.terminate()
    await chrome.worker.withRehydration('session', rehydrate)
    expect(chrome.worker.rehydrations).toBe(2)
    expect(chrome.worker.generation).toBe(1)
  })
})

describe('clock', () => {
  it('advances only when told', () => {
    expect(chrome.clock.now()).toBe(0)
    chrome.clock.advance(1_000)
    expect(chrome.clock.now()).toBe(1_000)
  })

  it('refuses to go backwards', () => {
    expect(() => chrome.clock.advance(-1)).toThrow(/backwards/)
  })
})

describe('reset', () => {
  it('clears storage, unlike a worker death', async () => {
    await chrome.storage.local.set({ a: 1 })
    chrome.reset()
    expect(await chrome.storage.local.get()).toEqual({})
  })
})
