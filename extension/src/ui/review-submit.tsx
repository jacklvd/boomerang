import { PencilSimpleIcon, WarningIcon } from '@phosphor-icons/react/dist/ssr'

import type { ReviewSummary } from '@/src/model/return-flow'
import { Button } from './button'
import { Heading, Notice } from './primitives'

/**
 * Frame 07 — the last reversible moment.
 *
 * Every field is editable from here, because this is the screen where a
 * misparse four steps back is still free to fix. After it, the return exists
 * on the retailer's side and Boomerang cannot take it back.
 */
export function ReviewSubmit({
  summary,
  onEdit,
  onSubmit,
  onChangeMethod,
}: {
  summary: ReviewSummary
  onEdit: (field: 'items' | 'reason' | 'method') => void
  onSubmit: () => void
  onChangeMethod: () => void
}) {
  const incomplete = summary.reason === null || summary.method === null

  return (
    <>
      <Heading
        title="Check this before we send it"
        body="Pre-filled from the steps above. Tap any field to change it."
      />

      <ul className="flex flex-col gap-2">
        <Field label="Items" value={summary.items} onEdit={() => onEdit('items')} />
        <Field label="Reason" value={summary.reason} onEdit={() => onEdit('reason')} />
        <Field label="Method" value={summary.method} onEdit={() => onEdit('method')} />
        {/* Not editable: Boomerang never chooses where the money goes. The
            retailer refunds the original payment method and nothing here can
            redirect that. */}
        <Field label="Refund to" value={summary.refundTo} />
      </ul>

      <div className="flex flex-col gap-2.5">
        <Button onClick={onSubmit} disabled={incomplete}>
          Confirm and submit
        </Button>
        <Button variant="ghost" onClick={onChangeMethod}>
          Go back and change the method
        </Button>
      </div>

      <Notice tone="quiet" icon={<WarningIcon size={13} className="text-warn" />}>
        Submitting starts the return with the retailer. We pause here because this step cannot be
        undone.
      </Notice>
    </>
  )
}

function Field({
  label,
  value,
  onEdit,
}: {
  label: string
  value: string | null
  onEdit?: () => void
}) {
  return (
    <li className="flex items-center gap-3 rounded-[10px] border border-line bg-surface px-3.5 py-3">
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-[11.5px] tracking-[0.04em] text-ink-faint uppercase">{label}</span>
        <span className={value ? 'text-[13px] text-ink' : 'text-[13px] text-ink-faint italic'}>
          {value ?? 'Not set'}
        </span>
      </span>
      {onEdit && (
        <button
          type="button"
          onClick={onEdit}
          aria-label={`Change ${label.toLowerCase()}`}
          className="shrink-0 text-ink-faint transition-colors hover:text-accent"
        >
          <PencilSimpleIcon size={15} />
        </button>
      )}
    </li>
  )
}
