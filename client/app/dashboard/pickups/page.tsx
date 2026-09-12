import type { Metadata } from 'next'
import { CheckCircle, Info, Package, Printer } from '@phosphor-icons/react/dist/ssr'

import { AppBar } from '@/components/dashboard/app-bar'
import { MOCK_ORDERS, MOCK_PAST_RETURNS, RETURN_STATE_LABELS, isActive } from '@/lib/orders'

export const metadata: Metadata = {
  title: 'Pickups — Boomerang',
}

/* D8: v1 is a carrier-neutral status view. No carrier name, no scheduling, no
   confirmation number, no address, no cancellation — the extension reports what
   it observed and this page renders it. */
export default function PickupsPage() {
  const active = MOCK_ORDERS.filter(isActive)
  const waiting = MOCK_ORDERS.filter((order) => !isActive(order))

  return (
    <>
      <AppBar current="/dashboard/pickups" />
      <main className="mx-auto flex w-full max-w-[1296px] flex-1 flex-col gap-10 px-6 py-10 md:px-10 lg:flex-row">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[32px] leading-[1.05] font-semibold tracking-[-0.02em] text-ink md:text-[38px]">
            Pickups
          </h1>
          <p className="mt-2 max-w-[64ch] text-[14.5px] text-ink-muted">
            Where each return has got to on its way out of your hands. Boomerang records what the
            retailer showed and what you confirmed &mdash; it does not book or track a courier.
          </p>

          <Group label="On the way">
            {active.map((order) => {
              const state = RETURN_STATE_LABELS[order.state]
              return (
                <li
                  key={order.id}
                  className="flex gap-4 rounded-[14px] border border-line bg-surface p-5"
                >
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-[11px] bg-accent-soft text-accent">
                    {order.state === 'label_ready' ? (
                      <Printer size={19} weight="bold" />
                    ) : (
                      <Package size={19} weight="bold" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[14.5px] font-semibold text-ink">{order.title}</p>
                    <p className="mt-1 text-[13px] text-ink-muted">{state.hint}</p>
                  </div>
                  <span className="h-fit shrink-0 rounded-full bg-accent-soft px-3 py-1.5 text-[12px] font-semibold text-accent">
                    {state.label}
                  </span>
                </li>
              )
            })}
          </Group>

          <Group label="Not started">
            {waiting.map((order) => (
              <li
                key={order.id}
                className="flex gap-4 rounded-[14px] border border-line bg-surface p-5"
              >
                <span className="flex size-10 shrink-0 items-center justify-center rounded-[11px] bg-bg text-ink-faint">
                  <Package size={19} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[14.5px] font-semibold text-ink">{order.title}</p>
                  <p className="mt-1 text-[13px] text-ink-muted">{order.blockedReason}</p>
                </div>
                <span className="h-fit shrink-0 rounded-full bg-bg px-3 py-1.5 text-[12px] font-semibold text-ink-faint">
                  {RETURN_STATE_LABELS[order.state].label}
                </span>
              </li>
            ))}
          </Group>

          <History />
        </div>

        <aside className="w-full shrink-0 lg:max-w-[320px]">
          <Scope />
        </aside>
      </main>
    </>
  )
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="text-[12.5px] font-semibold tracking-[0.1em] text-ink-faint uppercase">
        {label}
      </h2>
      <ul className="mt-3 flex flex-col gap-2.5">{children}</ul>
    </section>
  )
}

function History() {
  return (
    <section className="mt-10">
      <h2 className="text-[12.5px] font-semibold tracking-[0.1em] text-ink-faint uppercase">
        Handed over
      </h2>
      <div className="mt-3 overflow-hidden rounded-[14px] border border-line">
        <div className="hidden grid-cols-[1.4fr_1fr_1.1fr_auto] gap-6 border-b border-line bg-surface px-5 py-3 md:grid">
          {['Item', 'Retailer', 'Day', 'Status'].map((h) => (
            <span
              key={h}
              className="text-[11.5px] font-semibold tracking-[0.1em] text-ink-faint uppercase"
            >
              {h}
            </span>
          ))}
        </div>
        {MOCK_PAST_RETURNS.map((row) => (
          <div
            key={row.id}
            className="grid gap-1.5 border-b border-line bg-surface px-5 py-4 last:border-b-0 md:grid-cols-[1.4fr_1fr_1.1fr_auto] md:items-center md:gap-6"
          >
            <span className="text-[13.5px] font-medium text-ink">{row.title}</span>
            <span className="text-[13.5px] text-ink-muted">{row.retailer}</span>
            <span className="text-[13.5px] text-ink-muted">{row.on}</span>
            <span className="flex w-fit items-center gap-1.5 rounded-full bg-calm-soft px-2.5 py-1 text-[12px] font-semibold text-calm">
              <CheckCircle size={13} weight="fill" />
              Complete
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

function Scope() {
  return (
    <div className="rounded-[14px] border border-line bg-surface p-5">
      <p className="flex items-center gap-2 text-[11.5px] font-semibold tracking-[0.1em] text-ink-faint uppercase">
        <Info size={15} weight="bold" />
        What this page tracks
      </p>
      <p className="mt-3.5 text-[13px] leading-[1.55] text-ink-muted">
        A return moves forward here when the retailer&rsquo;s own page says it has, or when you
        confirm it yourself. Those are the only two sources.
      </p>
      <p className="mt-3 text-[13px] leading-[1.55] text-ink-muted">
        Boomerang does not schedule a courier, hold a confirmation number, or store your address. If
        a carrier ever collects from your door, that arrangement is between you and them.
      </p>
      <p className="mt-4 border-t border-line pt-4 text-[12px] leading-[1.5] text-ink-faint">
        Statuses reflect the last thing observed, not a live tracking feed.
      </p>
    </div>
  )
}
