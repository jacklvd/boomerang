/**
 * Stands in for the account data the dashboard will read from the server.
 *
 * dev-note: `daysLeft` is baked, not derived from `returnBy`, so the fixture
 * renders the same at build time and in the browser. Real countdown once the
 * API exists.
 */

/** Mirrors `ReturnState` in `server/app/models/domain.py`. */
export type ReturnState =
  'not_started' | 'in_progress' | 'qr_ready' | 'label_ready' | 'handed_to_carrier' | 'complete'

export type Order = {
  id: string
  title: string
  retailer: string
  deliveredOn: string
  returnBy: string
  price: number
  daysLeft: number
  state: ReturnState
  /** Why a return cannot start yet. Only meaningful while `not_started`. */
  blockedReason?: string
}

export const MOCK_ORDERS: Order[] = [
  {
    id: 'ord_coat',
    title: 'Wool Overcoat, Charcoal',
    retailer: 'Nordstrom',
    deliveredOn: '6 Aug',
    returnBy: '4 Sep',
    price: 180.0,
    daysLeft: 4,
    state: 'label_ready',
  },
  {
    id: 'ord_runners',
    title: 'Trail Runners, W 8.5',
    retailer: 'Amazon',
    deliveredOn: '8 Aug',
    returnBy: '6 Sep',
    price: 128.0,
    daysLeft: 6,
    state: 'in_progress',
  },
  {
    id: 'ord_lamp',
    title: 'Ceramic Table Lamp',
    retailer: 'Target',
    deliveredOn: '13 Aug',
    returnBy: '11 Sep',
    price: 64.0,
    daysLeft: 11,
    state: 'qr_ready',
  },
  {
    id: 'ord_sheets',
    title: 'Linen Sheet Set, Queen',
    retailer: 'Amazon',
    deliveredOn: '20 Aug',
    returnBy: '18 Sep',
    price: 95.0,
    daysLeft: 18,
    state: 'not_started',
    blockedReason: 'Nothing started yet. Open the order page and tap Scan.',
  },
  {
    id: 'ord_crew',
    title: 'Merino Crew Neck, Navy',
    retailer: 'Uniqlo',
    deliveredOn: '22 Aug',
    returnBy: '20 Sep',
    price: 59.0,
    daysLeft: 20,
    state: 'not_started',
    blockedReason: 'Nothing started yet. Open the order page and tap Scan.',
  },
  {
    id: 'ord_skillet',
    title: 'Cast Iron Skillet, 12 inch',
    retailer: 'Target',
    deliveredOn: '25 Aug',
    returnBy: '23 Sep',
    price: 48.0,
    daysLeft: 23,
    state: 'not_started',
    blockedReason: 'Nothing started yet. Open the order page and tap Scan.',
  },
]

/** Returns already handed over, shown as history rather than as open work. */
export const MOCK_PAST_RETURNS = [
  { id: 'past_1', title: 'Ribbed Beanie, Rust', retailer: 'Uniqlo', on: 'Wednesday, 19 August' },
  { id: 'past_2', title: 'Chef Knife, 8 inch', retailer: 'Target', on: 'Tuesday, 4 August' },
  { id: 'past_3', title: 'Cotton Chinos, 32', retailer: 'Nordstrom', on: 'Monday, 28 July' },
]

export type Urgency = 'urgent' | 'warn' | 'calm'

/**
 * Colour is data here, never decoration. Thresholds match the legend rendered
 * on the dashboard — change the two together or the page starts lying.
 *
 * dev-note: the server's `UrgencyLevel` enum is the eventual home for this, but
 * it carries no thresholds yet.
 */
export function urgencyOf(daysLeft: number): Urgency {
  if (daysLeft <= 7) return 'urgent'
  if (daysLeft <= 14) return 'warn'
  return 'calm'
}

export const URGENCY_CLASSES: Record<Urgency, { badge: string; dot: string; text: string }> = {
  urgent: { badge: 'bg-urgent-soft', dot: 'bg-urgent', text: 'text-urgent' },
  warn: { badge: 'bg-warn-soft', dot: 'bg-warn', text: 'text-warn' },
  calm: { badge: 'bg-calm-soft', dot: 'bg-calm', text: 'text-calm' },
}

export const URGENCY_LEGEND: { tone: Urgency; label: string; range: string }[] = [
  { tone: 'urgent', label: 'Urgent', range: '7 days or fewer' },
  { tone: 'warn', label: 'Soon', range: '8 to 14 days' },
  { tone: 'calm', label: 'Plenty of time', range: 'more than 14 days' },
]

/**
 * v1 tracks handoffs carrier-neutrally — no carrier name, no scheduling, no
 * confirmation number. See D8 in docs/ARCHITECTURE.md.
 */
export const RETURN_STATE_LABELS: Record<ReturnState, { label: string; hint: string }> = {
  not_started: { label: 'Not started', hint: 'No return has been opened for this order.' },
  in_progress: { label: 'In progress', hint: "The retailer's return flow is part-way through." },
  qr_ready: {
    label: 'QR code ready',
    hint: 'Show the code at a drop-off point. Nothing to print.',
  },
  label_ready: { label: 'Label ready', hint: 'Print it and attach it to the parcel.' },
  handed_to_carrier: { label: 'Handed over', hint: 'The parcel has left your hands.' },
  complete: { label: 'Complete', hint: 'The retailer has acknowledged the return.' },
}

const ACTIVE: ReturnState[] = ['in_progress', 'qr_ready', 'label_ready', 'handed_to_carrier']

export const isActive = (order: Order) => ACTIVE.includes(order.state)

export const totalAtRisk = (orders: Order[]) => orders.reduce((sum, order) => sum + order.price, 0)

export const closingThisWeek = (orders: Order[]) =>
  orders.filter((order) => urgencyOf(order.daysLeft) === 'urgent').length
