/**
 * Stands in for extension-owned data — the server is stateless, so there is no
 * `GET /orders` to call.
 *
 * dev-note: `daysLeft` is baked, not derived from `returnBy`, so the fixture
 * renders the same at build time and in the browser. Real countdown once the
 * extension feeds us.
 */
export type Order = {
  id: string
  title: string
  retailer: string
  deliveredOn: string
  returnBy: string
  price: number
  daysLeft: number
}

export const MOCK_ORDERS: Order[] = [
  {
    id: 'ord_coat',
    title: 'Wool Overcoat, Charcoal',
    retailer: 'Nordstrom',
    deliveredOn: 'Aug 5',
    returnBy: 'Sep 4',
    price: 180.0,
    daysLeft: 4,
  },
  {
    id: 'ord_runners',
    title: 'Trail Runners, W 8.5',
    retailer: 'Amazon',
    deliveredOn: 'Aug 10',
    returnBy: 'Sep 9',
    price: 128.0,
    daysLeft: 9,
  },
  {
    id: 'ord_lamp',
    title: 'Desk Lamp, Brass',
    retailer: 'Target',
    deliveredOn: 'Aug 15',
    returnBy: 'Sep 14',
    price: 64.0,
    daysLeft: 14,
  },
  {
    id: 'ord_sheets',
    title: 'Linen Sheet Set, Queen',
    retailer: 'Amazon',
    deliveredOn: 'Aug 19',
    returnBy: 'Sep 18',
    price: 95.0,
    daysLeft: 18,
  },
]

export type Urgency = 'urgent' | 'warn' | 'calm'

/** Colour is data here, never decoration — see the Color System board. */
export function urgencyOf(daysLeft: number): Urgency {
  if (daysLeft <= 7) return 'urgent'
  if (daysLeft <= 13) return 'warn'
  return 'calm'
}

export const URGENCY_CLASSES: Record<Urgency, { badge: string; dot: string; text: string }> = {
  urgent: { badge: 'bg-urgent-soft', dot: 'bg-urgent', text: 'text-urgent' },
  warn: { badge: 'bg-warn-soft', dot: 'bg-warn', text: 'text-warn' },
  calm: { badge: 'bg-calm-soft', dot: 'bg-calm', text: 'text-calm' },
}

export const totalAtRisk = (orders: Order[]) => orders.reduce((sum, order) => sum + order.price, 0)
