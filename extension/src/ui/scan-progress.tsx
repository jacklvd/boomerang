import { CheckCircleIcon, CircleIcon, CircleNotchIcon } from '@phosphor-icons/react/dist/ssr'

/**
 * Frame 02 — reading the page.
 *
 * The stages are a prop rather than a timer. The extractor that would report
 * them does not exist yet, and a screen that animated through four stages on a
 * setTimeout would be describing work nothing is doing.
 */
export type StageState = 'done' | 'running' | 'pending'
export type Stage = { label: string; state: StageState }

const MARK = {
  done: { Icon: CheckCircleIcon, className: 'text-calm' },
  running: { Icon: CircleNotchIcon, className: 'animate-spin text-accent' },
  pending: { Icon: CircleIcon, className: 'text-line' },
} as const

export function ScanProgress({ stages }: { stages: Stage[] }) {
  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 className="font-display text-[19px] leading-tight font-semibold text-ink">
          Reading the page…
        </h1>
        <p className="text-[13.5px] leading-[1.45] text-ink-muted">
          Extracting the order list. The page itself never leaves your browser whole.
        </p>
      </div>

      <ul className="flex flex-col gap-2.5">
        {stages.map(({ label, state }) => {
          const { Icon, className } = MARK[state]
          return (
            <li key={label} className="flex items-center gap-2.5">
              <Icon size={15} weight={state === 'pending' ? 'regular' : 'fill'} className={className} />
              <span
                className={`text-[13px] ${state === 'pending' ? 'text-ink-faint' : 'text-ink'}`}
              >
                {label}
              </span>
            </li>
          )
        })}
      </ul>

      <div aria-hidden className="flex flex-col gap-2">
        {[0, 1].map((row) => (
          <div key={row} className="flex items-center gap-3 rounded-[10px] bg-surface p-3">
            <div className="size-[34px] shrink-0 rounded-[6px] bg-bg" />
            <div className="flex w-full flex-col gap-2">
              <div className="h-2 w-full rounded-full bg-bg" />
              <div className="h-[7px] w-1/3 rounded-full bg-bg" />
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
