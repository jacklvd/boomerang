import { CheckSquareIcon, InfoIcon, SquareIcon } from '@phosphor-icons/react/dist/ssr'

import {
  daysUntil,
  formatDate,
  formatMoney,
  type ReadItem,
  type ReadOrder,
} from '@/src/model/read-order'
import { Button } from './button'

/**
 * Frame 03 — the order as Boomerang read it, for the user to confirm.
 *
 * This screen exists because the read can be wrong. Everything downstream — the
 * policy, the deadline, the method — is derived from what is confirmed here, so
 * it is the cheapest place to catch a misparse and the last place before one
 * starts costing something.
 */
export function OrderReview({
  order,
  selected,
  onToggle,
  onConfirm,
  onReject,
}: {
  order: ReadOrder
  selected: ReadonlySet<string>
  onToggle: (localId: string) => void
  onConfirm: () => void
  onReject: () => void
}) {
  const itemCount = order.items.length

  return (
    <>
      <h1 className="font-display text-[19px] leading-tight font-semibold text-ink">
        One order, {itemCount === 1 ? 'one item' : `${itemCount} items`}.
      </h1>

      <dl className="flex flex-col rounded-[10px] bg-surface px-4 py-1">
        <Meta label="Retailer" value={order.retailerName} />
        <Meta label="Order" value={order.orderReference} />
        <Meta label="Delivered" value={order.deliveredOn && formatDate(order.deliveredOn)} />
        <Meta
          label="Return by"
          value={order.returnBy && formatDate(order.returnBy)}
          trailing={order.returnBy ? <Countdown isoDate={order.returnBy} /> : null}
        />
      </dl>

      <ul className="flex flex-col gap-2">
        {order.items.map((item) => (
          <Item
            key={item.localId}
            item={item}
            checked={selected.has(item.localId)}
            onToggle={() => onToggle(item.localId)}
          />
        ))}
      </ul>

      <div className="flex flex-col gap-2.5">
        <Button onClick={onConfirm} disabled={selected.size === 0}>
          Looks right
        </Button>
        <Button variant="ghost" onClick={onReject}>
          Something is off
        </Button>
      </div>

      <p className="flex gap-2 text-[12px] leading-[1.45] text-ink-faint">
        <InfoIcon size={13} className="mt-0.5 shrink-0" />
        <span>
          Dates are read from the page, not guessed. The return-by date is the retailer&apos;s, and
          it can still be wrong at the edges.
        </span>
      </p>
    </>
  )
}

/** §3.4: a missing fact is shown as unknown, never filled in with a guess. */
function Meta({
  label,
  value,
  trailing,
}: {
  label: string
  value: string | null
  trailing?: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line py-2.5 last:border-0">
      <dt className="text-[12.5px] text-ink-faint">{label}</dt>
      <dd className="flex items-center gap-2 text-[12.5px] text-ink">
        <span className={value ? '' : 'text-ink-faint italic'}>{value ?? 'Not shown'}</span>
        {trailing}
      </dd>
    </div>
  )
}

/**
 * A count of days, never a level.
 *
 * §4.7 puts the thresholds that separate `critical` from `soon` in server
 * configuration and forbids frontends from hardcoding day ranges — and this
 * screen runs before the popup has spoken to the server at all. Expired is the
 * one distinction that needs no threshold: the number is negative.
 */
function Countdown({ isoDate }: { isoDate: string }) {
  const days = daysUntil(isoDate)
  if (days === null) return null

  const expired = days < 0
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${
        expired ? 'bg-urgent-soft text-urgent' : 'bg-bg text-ink-muted'
      }`}
    >
      {expired ? 'Window closed' : `${days} ${days === 1 ? 'day' : 'days'}`}
    </span>
  )
}

function Item({
  item,
  checked,
  onToggle,
}: {
  item: ReadItem
  checked: boolean
  onToggle: () => void
}) {
  const Box = checked ? CheckSquareIcon : SquareIcon
  const meta = [item.variant, `Qty ${item.quantity}`].filter(Boolean).join(' · ')

  return (
    <li>
      <label
        className={`flex cursor-pointer items-center gap-3 rounded-[10px] border bg-surface p-3 transition-colors ${
          checked ? 'border-accent' : 'border-line'
        }`}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          className="sr-only"
          aria-label={item.description}
        />
        <Box
          size={18}
          weight={checked ? 'fill' : 'regular'}
          className={checked ? 'shrink-0 text-accent' : 'shrink-0 text-ink-faint'}
        />
        <div aria-hidden className="size-8 shrink-0 rounded-[6px] bg-bg" />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[13px] text-ink">{item.description}</span>
          <span className="text-[12px] text-ink-faint">{meta}</span>
        </div>
        <span className="text-[13px] font-semibold text-ink">
          {item.price ? formatMoney(item.price) : '—'}
        </span>
      </label>
    </li>
  )
}
