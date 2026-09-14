import { CircleIcon, RadioButtonIcon } from '@phosphor-icons/react/dist/ssr'

import { cn } from './cn'

/**
 * The pieces frames 04 through 07 share.
 *
 * Extracted because four screens needed them, not in anticipation of a fifth.
 * Each one exists to stop the same decision being made four slightly different
 * ways — particularly `Fact`, where "unknown" has to look unmistakably unlike
 * "free" or "none".
 */

export function Heading({ title, body }: { title: string; body?: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="font-display text-[19px] leading-tight font-semibold text-ink">{title}</h1>
      {body && <p className="text-[13.5px] leading-[1.45] text-ink-muted">{body}</p>}
    </div>
  )
}

/** A radio row. Used for reasons and for return methods. */
export function ChoiceRow({
  selected,
  onSelect,
  label,
  description,
  trailing,
  badge,
}: {
  selected: boolean
  onSelect: () => void
  label: string
  description?: string
  trailing?: React.ReactNode
  badge?: string
}) {
  const Mark = selected ? RadioButtonIcon : CircleIcon
  return (
    <li>
      <label
        className={cn(
          'flex cursor-pointer gap-3 rounded-[10px] border p-3 transition-colors',
          selected ? 'border-accent bg-accent-soft' : 'border-line bg-surface hover:bg-bg',
        )}
      >
        <input type="radio" checked={selected} onChange={onSelect} className="sr-only" />
        <Mark
          size={17}
          weight={selected ? 'fill' : 'regular'}
          className={cn('mt-0.5 shrink-0', selected ? 'text-accent' : 'text-ink-faint')}
        />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="text-[13px] font-semibold text-ink">{label}</span>
            {trailing}
          </span>
          {description && (
            <span className="text-[12.5px] leading-[1.4] text-ink-muted">{description}</span>
          )}
          {badge && (
            <span className="mt-1 w-fit rounded-full bg-calm-soft px-2 py-0.5 text-[11px] font-semibold text-calm">
              {badge}
            </span>
          )}
        </span>
      </label>
    </li>
  )
}

/**
 * One parsed fact.
 *
 * `value` is nullable on purpose. §3.4 forbids inventing a fact to replace an
 * unknown one, and a return fee is the case that matters: §6.4 says `null` does
 * not mean free. "Not stated" in italic grey must never be mistaken for "None".
 */
export function Fact({
  icon,
  label,
  value,
  note,
}: {
  icon: React.ReactNode
  label: string
  value: string | null
  note?: string | null
}) {
  return (
    <li className="flex gap-3 border-b border-line px-3.5 py-3 last:border-0">
      <span className="mt-0.5 shrink-0 text-ink-faint">{icon}</span>
      <span className="flex flex-col gap-0.5">
        <span className="text-[11.5px] tracking-[0.04em] text-ink-faint uppercase">{label}</span>
        <span className={cn('text-[13px]', value ? 'text-ink' : 'text-ink-faint italic')}>
          {value ?? 'Not stated'}
        </span>
        {note && <span className="text-[11.5px] text-ink-faint">{note}</span>}
      </span>
    </li>
  )
}

export function Panel({ children }: { children: React.ReactNode }) {
  return <ul className="flex flex-col rounded-[10px] bg-surface">{children}</ul>
}

export function Notice({
  tone = 'warn',
  icon,
  children,
}: {
  tone?: 'warn' | 'urgent' | 'quiet'
  icon?: React.ReactNode
  children: React.ReactNode
}) {
  const tones = {
    warn: 'bg-warn-soft text-warn',
    urgent: 'bg-urgent-soft text-urgent',
    quiet: 'text-ink-faint',
  } as const
  return (
    <p className={cn('flex gap-2 rounded-[10px] text-[12px] leading-[1.45]', tones[tone], tone !== 'quiet' && 'px-3 py-2.5')}>
      {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
      <span>{children}</span>
    </p>
  )
}
