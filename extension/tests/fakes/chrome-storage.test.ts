import { beforeEach, describe, expect, it } from 'vitest'

import {
  DEFAULT_QUOTA_BYTES,
  FakeChromeStorage,
  QuotaExceededError,
  measure,
} from './chrome-storage'

let storage: FakeChromeStorage

beforeEach(() => {
  storage = new FakeChromeStorage()
})

describe('reads and writes', () => {
  it('round-trips a value', async () => {
    await storage.set({ session: { step: 'choose' } })
    expect(await storage.get('session')).toEqual({ session: { step: 'choose' } })
  })

  it('returns only the keys asked for, and omits missing ones', async () => {
    await storage.set({ a: 1, b: 2 })
    expect(await storage.get(['a', 'missing'])).toEqual({ a: 1 })
  })

  it('returns everything when asked for nothing', async () => {
    await storage.set({ a: 1, b: 2 })
    expect(await storage.get()).toEqual({ a: 1, b: 2 })
  })

  it('hands back a copy, so a caller cannot mutate the store through it', async () => {
    await storage.set({ session: { step: 'choose' } })
    const first = (await storage.get('session')) as { session: { step: string } }
    first.session.step = 'mutated'
    expect(await storage.get('session')).toEqual({ session: { step: 'choose' } })
  })

  it('removes and clears', async () => {
    await storage.set({ a: 1, b: 2, c: 3 })
    await storage.remove(['a', 'b'])
    expect(await storage.get()).toEqual({ c: 3 })
    await storage.clear()
    expect(await storage.get()).toEqual({})
  })
})

describe('atomicity', () => {
  it('leaves no partial write when a multi-key set is rejected', async () => {
    await storage.set({ existing: 'kept' })

    storage.armQuotaRejection()
    await expect(storage.set({ a: 1, b: 2, c: 3 })).rejects.toBeInstanceOf(QuotaExceededError)

    expect(await storage.get()).toEqual({ existing: 'kept' })
  })

  it('does not span two separate set calls — the reason checkpoints exist', async () => {
    await storage.set({ step: 'chosen' })
    storage.armQuotaRejection()
    await expect(storage.set({ label: 'ready' })).rejects.toThrow()

    // The first write stands alone. Nothing rolls it back, which is exactly the
    // torn state the real API allows and the design has to survive.
    expect(await storage.get()).toEqual({ step: 'chosen' })
  })
})

describe('quota', () => {
  it('rejects a write that would exceed the quota', async () => {
    const small = new FakeChromeStorage(64)
    await expect(small.set({ big: 'x'.repeat(200) })).rejects.toBeInstanceOf(QuotaExceededError)
    expect(await small.get()).toEqual({})
  })

  it('reports the pre-failure state after a rejection', async () => {
    await storage.set({ a: 'kept' })
    const before = await storage.getBytesInUse()

    storage.armQuotaRejection()
    await expect(storage.set({ b: 'x'.repeat(100) })).rejects.toThrow()

    expect(await storage.getBytesInUse()).toBe(before)
  })

  it('arms exactly one rejection', async () => {
    storage.armQuotaRejection()
    await expect(storage.set({ a: 1 })).rejects.toThrow()
    await expect(storage.set({ a: 1 })).resolves.toBeUndefined()
  })

  it('defaults to Chrome’s documented local quota', () => {
    expect(DEFAULT_QUOTA_BYTES).toBe(10 * 1024 * 1024)
  })
})

describe('getBytesInUse', () => {
  it('is computed from the serialized value, not stubbed', async () => {
    await storage.set({ k: 'abc' })
    expect(await storage.getBytesInUse('k')).toBe(measure('k', 'abc'))
    expect(await storage.getBytesInUse('k')).toBe(1 + 5) // "k" + "abc" with quotes
  })

  it('grows with writes and shrinks with removes', async () => {
    const empty = await storage.getBytesInUse()
    expect(empty).toBe(0)

    await storage.set({ a: 'x'.repeat(50) })
    const afterWrite = await storage.getBytesInUse()
    expect(afterWrite).toBeGreaterThan(empty)

    await storage.set({ b: 'y'.repeat(50) })
    expect(await storage.getBytesInUse()).toBeGreaterThan(afterWrite)

    await storage.remove('b')
    expect(await storage.getBytesInUse()).toBe(afterWrite)
  })

  it('scopes to the keys asked for', async () => {
    await storage.set({ a: 'aaa', b: 'bbb' })
    expect(await storage.getBytesInUse('a')).toBe(measure('a', 'aaa'))
    expect(await storage.getBytesInUse(['a', 'b'])).toBe(
      measure('a', 'aaa') + measure('b', 'bbb'),
    )
  })

  it('ignores keys that are not there', async () => {
    await storage.set({ a: 'aaa' })
    expect(await storage.getBytesInUse(['a', 'ghost'])).toBe(measure('a', 'aaa'))
  })
})
