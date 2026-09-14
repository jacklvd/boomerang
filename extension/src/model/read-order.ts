/**
 * What one scan read off one retailer page, before any of it has been stored.
 *
 * **This is not the ingestion wire contract.** The API contract lists
 * "order-page ingestion and normalization" under deferred contracts, so no
 * agreed shape exists for what the extension posts up. Inventing one here and
 * treating it as settled is exactly the mistake `plan/tasks/` made.
 *
 * What it *is*: the fields the popup has to render, named after the persistence
 * records that already define them — `Order`, `OrderItem` and `ReturnPolicy` in
 * data-model §6. When the ingestion contract lands, the names should already
 * line up; if they do not, this file changes and nothing else has to.
 */
import type { Money } from './workflow'

export type ReadItem = {
  /** Local to this read. Not an `OrderItem.id` — the server has not seen it. */
  localId: string
  /** §6.3 `description`. */
  description: string
  /** §6.3 `variant` — size, colour, or other concise variant text. */
  variant: string | null
  quantity: number
  /** §6.3: already covers the row's quantity. Never multiply it again. */
  price: Money | null
}

export type ReadOrder = {
  /** §6.2 `retailer_name`. */
  retailerName: string
  /** §6.2 `retailer_order_reference`. Null when the page does not show one. */
  orderReference: string | null
  /** ISO full date, or null. §3.4: never invented to replace a missing fact. */
  deliveredOn: string | null
  /** §6.4 `return_by`. The deadline as the page stated it. */
  returnBy: string | null
  items: ReadItem[]
}

const DATE = /^\d{4}-\d{2}-\d{2}$/

/**
 * Whole days from today to an ISO date. Negative means the deadline has passed.
 *
 * Deliberately returns a number and never an `UrgencyLevel`. §4.7 puts the
 * thresholds that separate `critical` from `soon` in server configuration and
 * says frontends must not hardcode day ranges — and at this point in the flow
 * the popup has not spoken to the server at all, so it does not have them.
 * A count is arithmetic on a date the page stated. A level would be a guess
 * wearing the vocabulary's clothes.
 */
export function daysUntil(isoDate: string, today = new Date()): number | null {
  if (!DATE.test(isoDate)) return null

  const [y, m, d] = isoDate.split('-').map(Number) as [number, number, number]
  const deadline = Date.UTC(y, m - 1, d)
  /* Both sides collapse to UTC midnight of a calendar day, so the answer does
     not shift with the clock or a DST boundary partway through the window. */
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())

  const days = Math.round((deadline - start) / 86_400_000)
  return Number.isFinite(days) ? days : null
}

export function formatMoney({ amount_minor, currency }: Money): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(
    amount_minor / 100,
  )
}

/** `5 September 2026`. Parsed as UTC so the day never slips backwards. */
export function formatDate(isoDate: string): string {
  if (!DATE.test(isoDate)) return isoDate
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${isoDate}T00:00:00Z`))
}

/**
 * Adds or removes one item from the confirmed selection.
 *
 * Returns a new set rather than mutating: React only re-renders on a changed
 * reference, so a mutated set would leave the checkbox showing the old state.
 */
export function toggleSelection(selected: ReadonlySet<string>, localId: string): Set<string> {
  const next = new Set(selected)
  if (!next.delete(localId)) next.add(localId)
  return next
}

/** Fixture dates are relative so the preview does not quietly rot into an
 *  expired window a month after anyone last looked at it. */
function isoDaysFromToday(offset: number): string {
  const date = new Date()
  date.setDate(date.getDate() + offset)
  /* Built from local parts, not toISOString(): west of UTC, an evening
     `toISOString()` reports tomorrow, and the preview would be a day out. */
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/* dev-note: stands in for the extractor. The popup only reaches a screen that
   uses this under PREVIEW — the live flow stops at the scan count, because
   showing this order after a real scan would claim we read it off the page. */
export const FIXTURE_ORDER: ReadOrder = {
  retailerName: 'Nordstrom',
  orderReference: '#114-2280',
  deliveredOn: isoDaysFromToday(-30),
  returnBy: isoDaysFromToday(4),
  items: [
    {
      localId: 'read_1',
      description: 'Wool Overcoat, Charcoal',
      variant: 'Size M',
      quantity: 1,
      price: { amount_minor: 18000, currency: 'USD' },
    },
    {
      localId: 'read_2',
      description: 'Merino Scarf, Oat',
      variant: null,
      quantity: 1,
      price: { amount_minor: 4800, currency: 'USD' },
    },
  ],
}
