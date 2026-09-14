import { CheckIcon, LockSimpleIcon } from '@phosphor-icons/react/dist/ssr'

import { formatDate } from '@/src/model/read-order'
import { Button } from './button'
import { Heading, Notice } from './primitives'

export type FinishedSummary = {
  item: string
  method: string
  /** The retailer's own reference. Null when they did not give one. */
  reference: string | null
  refund: string
  /** ISO date. Null when no deadline was stated. */
  dropOffBy: string | null
}

/**
 * Frame 11 — the run is over.
 *
 * "The hard part is done", not "that one is handled". The extension's run has
 * reached `terminal`; the *return* has not reached `complete`, which is blocked
 * on ARCH-B8 and in any case waits on the user walking to a counter. Claiming
 * otherwise here would be the screen asserting a state the vocabulary forbids
 * anyone from writing.
 */
export function Finished({
  summary,
  onSeeReturns,
}: {
  summary: FinishedSummary
  onSeeReturns: () => void
}) {
  return (
    <>
      <span className="mx-auto flex size-[54px] items-center justify-center rounded-full bg-calm-soft">
        <CheckIcon size={25} weight="bold" className="text-calm" />
      </span>

      <div className="text-center">
        <Heading
          title="The hard part is done."
          body={
            summary.dropOffBy
              ? `Drop it off by ${formatDate(summary.dropOffBy)}. The reminder is saved.`
              : 'The retailer did not state a drop-off deadline.'
          }
        />
      </div>

      <ul className="flex flex-col rounded-[10px] bg-surface">
        <Row label="Item" value={summary.item} />
        <Row label="Method" value={summary.method} />
        <Row label="Confirmation" value={summary.reference} />
        <Row label="Refund" value={summary.refund} />
      </ul>

      <Button onClick={onSeeReturns}>See all my returns</Button>

      <Notice tone="quiet" icon={<LockSimpleIcon size={13} className="text-calm" />}>
        Saved on this machine only. Our server kept nothing from this flow.
      </Notice>
    </>
  )
}

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <li className="flex items-baseline justify-between gap-4 border-b border-line px-3.5 py-3 last:border-0">
      <span className="shrink-0 text-[12.5px] text-ink-faint">{label}</span>
      <span
        className={
          value ? 'text-right text-[12.5px] text-ink' : 'text-[12.5px] text-ink-faint italic'
        }
      >
        {value ?? 'Not given'}
      </span>
    </li>
  )
}
