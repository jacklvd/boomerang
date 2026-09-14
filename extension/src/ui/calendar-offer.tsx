import { CalendarBlankIcon, InfoIcon } from '@phosphor-icons/react/dist/ssr'

import { ISO_DATE, formatDate } from '@/src/model/read-order'
import { Button } from './button'
import { Heading, Notice } from './primitives'

/**
 * Frame 10 — the deadline reminder.
 *
 * D3 is the shape of this: Calendar creates a deadline or follow-up reminder,
 * and does not read free/busy or pick a time from the user's schedule. So the
 * screen opens a prefilled event in a tab and lets the user save it themselves
 * — no Google account on our side, no scope, nothing stored.
 *
 * The event is the *deadline*, not a collection. D4 and D6 deferred carrier
 * pickup, so an event promising that a carrier arrives would describe a feature
 * that does not exist.
 */
export function CalendarOffer({
  retailerName,
  returnBy,
  onOpenCalendar,
  onDecline,
}: {
  retailerName: string
  returnBy: string
  onOpenCalendar: () => void
  onDecline: () => void
}) {
  /* Same guard as `formatDate`: a string that is not `YYYY-MM-DD` would render
     an "Invalid Date" tile. A reminder needs a day; without one there is no
     offer to make, and the caller should not have reached this frame. */
  if (!ISO_DATE.test(returnBy)) return null

  const date = new Date(`${returnBy}T00:00:00Z`)
  const month = new Intl.DateTimeFormat('en-GB', { month: 'short', timeZone: 'UTC' })
    .format(date)
    .toUpperCase()
  const day = new Intl.DateTimeFormat('en-GB', { day: 'numeric', timeZone: 'UTC' }).format(date)
  const weekday = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: 'UTC' }).format(
    date,
  )

  return (
    <>
      <Heading
        title="Put it on the calendar?"
        body="We open a prefilled event in a new tab. You review it and save it yourself."
      />

      <div className="flex flex-col gap-3 rounded-[10px] bg-surface p-4">
        <div className="flex gap-3">
          <span className="flex size-[52px] shrink-0 flex-col items-center justify-center rounded-[8px] bg-accent-soft">
            <span className="text-[11px] font-semibold tracking-[0.06em] text-accent">{month}</span>
            <span className="font-display text-[20px] leading-none font-semibold text-accent">
              {day}
            </span>
          </span>
          <span className="flex flex-col gap-0.5">
            <span className="text-[13.5px] font-semibold text-ink">
              {retailerName} return — last day
            </span>
            <span className="text-[12.5px] text-ink-faint">{weekday} · all day</span>
          </span>
        </div>

        <div className="h-px bg-line" />

        <p className="text-[12.5px] leading-[1.45] text-ink-muted">
          A reminder to drop the parcel off. {retailerName}&apos;s return window closes on{' '}
          {formatDate(returnBy)} — the deadline Boomerang read off the policy, not a time the
          retailer promised.
        </p>
      </div>

      <div className="flex flex-col gap-2.5">
        <Button onClick={onOpenCalendar}>
          <CalendarBlankIcon size={16} weight="bold" />
          Open in my calendar
        </Button>
        <Button variant="ghost" onClick={onDecline}>
          No thanks
        </Button>
      </div>

      <Notice tone="quiet" icon={<InfoIcon size={13} className="text-warn" />}>
        This is the one thing we send to Google, and only because you asked. We hold no Google
        account and store nothing of theirs.
      </Notice>
    </>
  )
}
