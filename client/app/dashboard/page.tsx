import type { Metadata } from 'next'
import { CaretDown, Plugs } from '@phosphor-icons/react/dist/ssr'

import { AppBar, EXTENSION_CONNECTED } from '@/components/dashboard/app-bar'
import { OrderRow } from '@/components/order-row'
import { InstallCard } from '@/components/landing/install-card'
import {
  MOCK_ORDERS,
  URGENCY_CLASSES,
  URGENCY_LEGEND,
  closingThisWeek,
  isActive,
  totalAtRisk,
} from '@/lib/orders'
import { cn } from '@/lib/utils'

export const metadata: Metadata = {
  title: 'Your returns — Boomerang',
}

export default function DashboardPage() {
  if (!EXTENSION_CONNECTED) {
    return (
      <>
        <AppBar current="/dashboard" />
        <EmptyState />
      </>
    )
  }

  const orders = [...MOCK_ORDERS].sort((a, b) => a.daysLeft - b.daysLeft)

  return (
    <>
      <AppBar current="/dashboard" />
      <main className="mx-auto flex w-full max-w-[1296px] flex-1 flex-col gap-10 px-6 py-10 md:px-10 lg:flex-row">
        <div className="min-w-0 flex-1">
          <PageHead />
          <Stats orders={orders} />

          <p className="mt-10 text-[12.5px] font-semibold tracking-[0.1em] text-ink-faint uppercase">
            Closing soonest
          </p>
          <div className="mt-3 flex flex-col gap-2.5">
            {orders.map((order) => (
              <OrderRow key={order.id} order={order} className="border border-line" />
            ))}
          </div>
        </div>

        <aside className="w-full shrink-0 lg:max-w-[320px]">
          <Legend />
        </aside>
      </main>
    </>
  )
}

function PageHead() {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-[32px] leading-[1.05] font-semibold tracking-[-0.02em] text-ink md:text-[38px]">
          Your returns
        </h1>
        <p className="mt-2 max-w-[60ch] text-[14.5px] text-ink-muted">
          Deadlines are recomputed each time this page loads, never read back from a stored
          countdown.
        </p>
      </div>

      {/* dev-note: display-only until there is more than one ordering to pick. */}
      <span className="flex items-center gap-2 rounded-[10px] border border-line bg-surface px-3.5 py-2.5 text-[13.5px] text-ink-muted">
        Closing soonest
        <CaretDown size={14} className="text-ink-faint" />
      </span>
    </div>
  )
}

function Stats({ orders }: { orders: typeof MOCK_ORDERS }) {
  const stats = [
    { label: 'Closing this week', value: String(closingThisWeek(orders)) },
    { label: 'Still returnable', value: `$${totalAtRisk(orders).toFixed(2)}` },
    { label: 'Returns in progress', value: String(orders.filter(isActive).length) },
  ]

  return (
    <dl className="mt-7 grid gap-px overflow-hidden rounded-[14px] border border-line bg-line sm:grid-cols-3">
      {stats.map((stat) => (
        <div key={stat.label} className="bg-surface px-6 py-5">
          <dt className="text-[12.5px] font-semibold tracking-[0.1em] text-ink-faint uppercase">
            {stat.label}
          </dt>
          <dd className="mt-2 font-display text-[30px] leading-none font-semibold text-ink">
            {stat.value}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function Legend() {
  return (
    <div className="rounded-[14px] border border-line bg-surface p-5">
      <p className="text-[11.5px] font-semibold tracking-[0.1em] text-ink-faint uppercase">
        How urgency is set
      </p>
      <ul className="mt-4 flex flex-col gap-3">
        {URGENCY_LEGEND.map((row) => (
          <li key={row.tone} className="flex items-center gap-2.5">
            <span
              className={cn('size-[7px] shrink-0 rounded-full', URGENCY_CLASSES[row.tone].dot)}
              aria-hidden
            />
            <span className="text-[13.5px] font-medium text-ink">{row.label}</span>
            <span className="ml-auto text-[12.5px] text-ink-muted">{row.range}</span>
          </li>
        ))}
      </ul>
      <p className="mt-4 border-t border-line pt-4 text-[12px] leading-[1.5] text-ink-faint">
        Counted from the return-by date at the moment you open this page, never from a stored
        countdown. Windows are estimates, not guarantees.
      </p>
    </div>
  )
}

function EmptyState() {
  return (
    <main className="mx-auto flex w-full max-w-[720px] flex-1 flex-col items-center px-6 py-24 text-center">
      <span className="flex size-16 items-center justify-center rounded-[18px] border border-line bg-surface">
        <Plugs size={28} className="text-ink-faint" />
      </span>
      <h1 className="mt-8 max-w-[18ch] font-display text-[28px] leading-[1.08] font-semibold tracking-[-0.02em] text-ink md:text-[34px]">
        This dashboard has nothing to show yet.
      </h1>
      <p className="mt-5 max-w-[54ch] text-[15.5px] leading-[1.55] text-ink-muted">
        Boomerang can only read an order page you are signed into, and only in your own browser.
        Until the extension is installed and has scanned one, there is nothing here to show.
      </p>
      <div className="mt-9 text-left">
        <InstallCard />
      </div>
    </main>
  )
}
