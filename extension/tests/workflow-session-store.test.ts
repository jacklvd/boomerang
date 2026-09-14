import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FakeChromeStorage } from './fakes/chrome-storage'
import { FakeWorkerLifecycle } from './fakes/worker-lifecycle'
import { WORKFLOW_SCHEMA_VERSION, type WorkflowSession } from '../src/model/workflow'
import { sessionKey, WorkflowSessionStore } from '../src/storage/workflow-session-store'

const sessionFor = (itemId: string): WorkflowSession => ({
  schema_version: WORKFLOW_SCHEMA_VERSION,
  id: `wfs_${itemId}`,
  account_id: 'acct_01',
  order_id: 'order_01',
  item_id: itemId,
  run_status: 'active',
  retailer_step: 'select_items',
  tab_id: 42,
  last_validated_url: 'https://retailer.example/returns/start',
  safe_checkpoint: null,
  fields_filled: [],
  suggested_reason: null,
  user_confirmed_reason: null,
  selected_return_method: null,
  attempt_count: 0,
  started_at: '2026-09-01T20:03:00Z',
  updated_at: '2026-09-01T20:03:00Z',
})

let area: FakeChromeStorage
let store: WorkflowSessionStore
let warn: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  area = new FakeChromeStorage()
  store = new WorkflowSessionStore(area)
  warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  warn.mockRestore()
})

describe('WorkflowSessionStore', () => {
  it('round-trips a session through storage', async () => {
    const session = sessionFor('item_01')
    await store.write(session)
    expect(await store.read('item_01')).toEqual(session)
  })

  it('returns null for an item with no session', async () => {
    expect(await store.read('item_99')).toBeNull()
  })

  it('keeps one session per item, keyed by the item (§9)', async () => {
    await store.write(sessionFor('item_01'))
    await store.write(sessionFor('item_02'))

    expect(await store.read('item_01')).toMatchObject({ id: 'wfs_item_01' })
    expect(await store.read('item_02')).toMatchObject({ id: 'wfs_item_02' })
    expect(await store.list()).toHaveLength(2)
  })

  it('does not collide when an opaque identifier contains the separator', async () => {
    await store.write(sessionFor('item:01'))
    await store.write(sessionFor('item'))

    expect(await store.read('item:01')).toMatchObject({ id: 'wfs_item:01' })
    expect(await store.read('item')).toMatchObject({ id: 'wfs_item' })
  })

  it('overwrites rather than accumulating', async () => {
    await store.write(sessionFor('item_01'))
    await store.write({ ...sessionFor('item_01'), attempt_count: 3, run_status: 'awaiting_user' })

    expect(await store.read('item_01')).toMatchObject({ attempt_count: 3 })
    expect(await store.list()).toHaveLength(1)
  })

  it('clears a session', async () => {
    await store.write(sessionFor('item_01'))
    await store.clear('item_01')
    expect(await store.read('item_01')).toBeNull()
  })

  it('discards an unreadable record instead of returning or keeping it', async () => {
    await area.set({ [sessionKey('item_01')]: { schema_version: 7 } })

    expect(await store.read('item_01')).toBeNull()
    expect(warn).toHaveBeenCalledOnce()

    /* The second read must find nothing at all — a record that survived would
       fail forever on every worker wake-up. */
    warn.mockClear()
    expect(await store.read('item_01')).toBeNull()
    expect(warn).not.toHaveBeenCalled()
    expect(await area.get(null)).toEqual({})
  })

  it('refuses to store content that could not be read back', async () => {
    const offsetTimestamp = { ...sessionFor('item_01'), started_at: '2026-09-01T20:03:00+05:00' }
    await expect(store.write(offsetTimestamp)).rejects.toThrow('started_at')

    const badUrl = { ...sessionFor('item_01'), last_validated_url: 'javascript:alert(1)' }
    await expect(store.write(badUrl)).rejects.toThrow('http(s)')

    expect(await area.get(null)).toEqual({})
  })

  it('lets a quota rejection surface rather than reporting a run it did not store', async () => {
    area.armQuotaRejection()
    await expect(store.write(sessionFor('item_01'))).rejects.toThrow('quota exceeded')
    expect(await store.read('item_01')).toBeNull()
  })

  it('ignores storage this store does not own', async () => {
    await area.set({ preferences: ['lowest_cost'], 'other:item_01': { id: 'x' } })
    await store.write(sessionFor('item_01'))

    expect(await store.list()).toHaveLength(1)
    expect(await area.get('preferences')).toEqual({ preferences: ['lowest_cost'] })
  })

  it('returns the readable sessions and drops the rest', async () => {
    await store.write(sessionFor('item_01'))
    await area.set({ [sessionKey('item_02')]: { page_html: '<html>' } })

    expect(await store.list()).toEqual([sessionFor('item_01')])
    expect(sessionKey('item_02') in (await area.get(null))).toBe(false)
  })

  it('survives worker death, and in-memory state does not', async () => {
    const worker = new FakeWorkerLifecycle()
    const load = () => worker.withRehydration('session', () => store.read('item_01'))

    await store.write(sessionFor('item_01'))
    expect(await load()).toMatchObject({ id: 'wfs_item_01' })
    expect(worker.rehydrations).toBe(1)

    /* A warm worker must not re-read; that is the whole reason for a cache. */
    await load()
    expect(worker.rehydrations).toBe(1)

    worker.terminate()
    expect(worker.recall('session')).toBeUndefined()
    expect(await load()).toMatchObject({ id: 'wfs_item_01' })
    expect(worker.rehydrations).toBe(2)
  })
})
