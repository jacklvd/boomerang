import { describe, expect, it } from 'vitest'

import {
  daysUntil,
  formatDate,
  formatMoney,
  toggleSelection,
  FIXTURE_ORDER,
} from '../src/model/read-order'

const on = (iso: string) => new Date(`${iso}T12:00:00Z`)

describe('daysUntil', () => {
  it('counts whole days to the deadline', () => {
    expect(daysUntil('2026-09-05', on('2026-09-01'))).toBe(4)
    expect(daysUntil('2026-09-01', on('2026-09-01'))).toBe(0)
  })

  it('goes negative once the window has closed', () => {
    expect(daysUntil('2026-08-30', on('2026-09-01'))).toBe(-2)
  })

  /* The count must not shift because the clock crossed a DST boundary
     partway through the window — both sides collapse to UTC midnight. */
  it('is stable across a daylight-saving change', () => {
    expect(daysUntil('2026-11-10', on('2026-10-30'))).toBe(11)
    expect(daysUntil('2026-04-05', on('2026-03-01'))).toBe(35)
  })

  it('crosses month and year boundaries', () => {
    expect(daysUntil('2027-01-01', on('2026-12-30'))).toBe(2)
    expect(daysUntil('2026-03-01', on('2026-02-27'))).toBe(2)
  })

  it('refuses anything that is not an ISO full date', () => {
    for (const bad of ['5 September 2026', '2026-9-5', '2026-09-05T00:00:00Z', '']) {
      expect(daysUntil(bad, on('2026-09-01')), bad).toBeNull()
    }
  })
})

describe('formatting', () => {
  it('renders minor units as money without touching the amount', () => {
    expect(formatMoney({ amount_minor: 18000, currency: 'USD' })).toBe('$180.00')
    expect(formatMoney({ amount_minor: 0, currency: 'USD' })).toBe('$0.00')
    expect(formatMoney({ amount_minor: 4899, currency: 'USD' })).toBe('$48.99')
  })

  /* Parsed as UTC, or a date before noon in a negative offset renders as the
     day before — the deadline the user is shown would be off by one. */
  it('does not let the local timezone move the date', () => {
    expect(formatDate('2026-09-05')).toBe('5 September 2026')
    expect(formatDate('2026-01-01')).toBe('1 January 2026')
  })

  it('passes a malformed date through rather than inventing one', () => {
    expect(formatDate('soon')).toBe('soon')
  })
})

describe('item selection', () => {
  const ids = FIXTURE_ORDER.items.map((item) => item.localId)

  it('toggles one item without disturbing the others', () => {
    const all = new Set(ids)
    const one = toggleSelection(all, ids[0]!)
    expect(one.has(ids[0]!)).toBe(false)
    expect(one.has(ids[1]!)).toBe(true)
    expect(toggleSelection(one, ids[0]!)).toEqual(all)
  })

  it('never mutates the set it was given', () => {
    const before = new Set(ids)
    toggleSelection(before, ids[0]!)
    expect(before).toEqual(new Set(ids))
  })
})

describe('the fixture', () => {
  /* It stands in for extracted data, so it has to be shaped like data a real
     page could produce — including the fact a page may not state a variant. */
  it('carries a missing fact as null rather than an empty string', () => {
    expect(FIXTURE_ORDER.items.some((item) => item.variant === null)).toBe(true)
    expect(FIXTURE_ORDER.items.every((item) => item.variant !== '')).toBe(true)
  })

  it('prices every item in whole minor units', () => {
    for (const item of FIXTURE_ORDER.items) {
      expect(Number.isInteger(item.price?.amount_minor)).toBe(true)
    }
  })
})

describe('fixture dates', () => {
  /* The helper that builds them is the same shape as the bug `formatDate`
     guards against: `toISOString()` west of UTC reports tomorrow after ~17:00. */
  it('are the local calendar dates they claim to be', () => {
    expect(daysUntil(FIXTURE_ORDER.returnBy!)).toBe(4)
    expect(daysUntil(FIXTURE_ORDER.deliveredOn!)).toBe(-30)
  })
})
