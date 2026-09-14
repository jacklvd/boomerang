import {
  ArrowCounterClockwiseIcon,
  CheckCircleIcon,
  CircleIcon,
  ClockIcon,
  DotOutlineIcon,
  WarningIcon,
} from '@phosphor-icons/react/dist/ssr'

import type { ResumeView, StepState } from '@/src/model/resume'
import { Button } from './button'
import { cn } from './cn'
import { Heading, Notice } from './primitives'

/**
 * Frame I3 — picking up a run that was left days ago.
 *
 * Everything time-dependent on this screen is recomputed. The draft says what
 * the user chose; it does not get to say how long is left, because the answer
 * changed every day it sat there. The deadline line says so out loud, because a
 * user looking at a restored draft has every reason to wonder whether the
 * numbers on it are as old as the draft.
 */
export function ResumeRun({
  view,
  itemDescription,
  retailerName,
  savedAt,
  onContinue,
  onStartOver,
}: {
  view: ResumeView
  itemDescription: string
  retailerName: string
  savedAt: string
  onContinue: () => void
  onStartOver: () => void
}) {
  return (
    <>
      <span className="flex w-fit items-center gap-2 rounded-full bg-accent-soft px-3 py-1.5">
        <ArrowCounterClockwiseIcon size={12} className="text-accent" />
        <span className="text-[11.5px] font-semibold tracking-[0.06em] text-accent uppercase">
          Restored from this browser
        </span>
      </span>

      <Heading
        title="Picking up where you stopped"
        body="Nothing was submitted. Your choices are as you left them."
      />

      <div className="flex items-center gap-3 rounded-[10px] bg-surface p-3">
        <span aria-hidden className="size-[38px] shrink-0 rounded-[6px] bg-bg" />
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-[13px] font-semibold text-ink">{itemDescription}</span>
          <span className="text-[12px] text-ink-faint">
            {retailerName} · saved {savedAt}
          </span>
        </span>
      </div>

      <ul className="flex flex-col gap-2.5">
        {view.steps.map((step) => (
          <Step key={step.label} label={step.label} state={step.state} />
        ))}
      </ul>

      <Deadline view={view} />

      <div className="flex flex-col gap-2.5">
        <Button onClick={onContinue} disabled={!view.resumable}>
          {view.resumable ? 'Continue from here' : 'That tab is gone'}
        </Button>
        <Button variant="ghost" onClick={onStartOver}>
          Start this return over
        </Button>
      </div>
    </>
  )
}

/**
 * The deadline, always stated as recomputed.
 *
 * An expired window is urgent rather than a warning: the draft is no longer
 * actionable and saying so quietly would be the wrong volume. An unknown
 * deadline says nothing at all rather than implying there is time (§3.4).
 */
function Deadline({ view }: { view: ResumeView }) {
  if (view.daysRemaining === null) {
    return (
      <Notice tone="quiet" icon={<ClockIcon size={13} />}>
        No return deadline was stated for this item, so there is nothing to count down.
      </Notice>
    )
  }

  if (view.expired) {
    return (
      <Notice tone="urgent" icon={<WarningIcon size={14} weight="fill" />}>
        The window closed {Math.abs(view.daysRemaining)}{' '}
        {Math.abs(view.daysRemaining) === 1 ? 'day' : 'days'} ago. Checked against today, not the
        date saved with the draft.
      </Notice>
    )
  }

  return (
    <Notice tone="warn" icon={<ClockIcon size={14} />}>
      The window closes in {view.daysRemaining} {view.daysRemaining === 1 ? 'day' : 'days'}.
      Re-checked against today's date, not the one saved with the draft.
    </Notice>
  )
}

const MARK: Record<StepState, { Icon: typeof CircleIcon; className: string }> = {
  done: { Icon: CheckCircleIcon, className: 'text-calm' },
  current: { Icon: DotOutlineIcon, className: 'text-warn' },
  pending: { Icon: CircleIcon, className: 'text-line' },
}

function Step({ label, state }: { label: string; state: StepState }) {
  const { Icon, className } = MARK[state]
  return (
    <li className="flex items-center gap-2.5">
      <Icon size={15} weight={state === 'pending' ? 'regular' : 'fill'} className={className} />
      <span className={cn('text-[13px]', state === 'pending' ? 'text-ink-faint' : 'text-ink')}>
        {label}
      </span>
    </li>
  )
}
