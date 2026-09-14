import {
  CheckCircleIcon,
  CircleIcon,
  CircleNotchIcon,
  ShieldCheckIcon,
  WarningCircleIcon,
  XCircleIcon,
} from '@phosphor-icons/react/dist/ssr'

import { isStuck, type LogEntry, type StepState } from '@/src/model/agent-log'
import { Button } from './button'
import { cn } from './cn'
import { Heading, Notice } from './primitives'

/**
 * Frames 08 and E1 — the agent running, and the agent giving up.
 *
 * One component, because they are the same screen at two points: a log, a
 * heading that describes where it got to, and an exit. Splitting them would
 * mean keeping two copies of the log in step for no gain.
 *
 * The run happens in a visible tab. That is not a UI flourish — a driver the
 * user cannot watch is one they cannot take over from, and taking over is the
 * documented fallback for every case the agent cannot handle.
 */
export function DriverLog({
  entries,
  deadlineNote,
  onTakeOver,
  onReport,
}: {
  entries: LogEntry[]
  /** Frame E1 restates the deadline, because a failed run is not a lost return. */
  deadlineNote?: string
  onTakeOver: () => void
  onReport?: () => void
}) {
  const stuck = isStuck(entries)

  return (
    <>
      {stuck && (
        <span className="flex w-fit items-center gap-2 rounded-full bg-urgent-soft px-3 py-1.5">
          <WarningCircleIcon size={12} weight="fill" className="text-urgent" />
          <span className="text-[11.5px] font-semibold tracking-[0.06em] text-urgent uppercase">
            Nothing was submitted
          </span>
        </span>
      )}

      <Heading
        title={stuck ? 'We could not finish this one' : 'Filling in the return form…'}
        body={
          stuck
            ? 'The return page changed in a way the agent does not recognise. It stopped rather than guess.'
            : 'Running in a visible tab so you can watch it. Take over at any point.'
        }
      />

      <ul className="flex flex-col gap-2.5">
        {/* The log is append-only, so position is the identity of a line. Tool and
            target are not: a run can click the same control twice. */}
        {entries.map((entry, index) => (
          <Step key={index} label={entry.label} state={entry.state} />
        ))}
      </ul>

      {stuck && deadlineNote && (
        <div className="flex flex-col gap-1 rounded-[10px] bg-surface p-3.5">
          <span className="text-[11.5px] font-semibold tracking-[0.04em] text-ink-faint uppercase">
            Your return is unaffected
          </span>
          <span className="text-[12.5px] leading-[1.45] text-ink-muted">{deadlineNote}</span>
        </div>
      )}

      <div className="flex flex-col gap-2.5">
        <Button onClick={onTakeOver} variant={stuck ? 'primary' : 'ghost'}>
          {stuck ? 'Take me to the page' : 'Pause and let me drive'}
        </Button>
        {stuck && onReport && (
          <Button variant="ghost" onClick={onReport}>
            Tell us what broke
          </Button>
        )}
      </div>

      <Notice tone="quiet" icon={<ShieldCheckIcon size={13} className="text-calm" />}>
        {stuck
          ? 'We keep the step that failed, never the page content.'
          : 'The agent can only click, select, fill and pause. It never types into a password, payment or upload field.'}
      </Notice>
    </>
  )
}

const MARK: Record<StepState, { Icon: typeof CircleIcon; className: string }> = {
  done: { Icon: CheckCircleIcon, className: 'text-calm' },
  running: { Icon: CircleNotchIcon, className: 'animate-spin text-accent' },
  failed: { Icon: XCircleIcon, className: 'text-urgent' },
  pending: { Icon: CircleIcon, className: 'text-line' },
}

function Step({ label, state }: { label: string; state: StepState }) {
  const { Icon, className } = MARK[state]
  return (
    <li className="flex items-center gap-2.5">
      {/* A notch filled is just a dot. `running` has to look unmistakably
          unlike `done`, so it keeps its arc. */}
      <Icon
        size={15}
        weight={state === 'done' || state === 'failed' ? 'fill' : 'bold'}
        className={className}
      />
      <span className={cn('text-[13px]', state === 'pending' ? 'text-ink-faint' : 'text-ink')}>
        {label}
      </span>
    </li>
  )
}
