import { InfoIcon } from '@phosphor-icons/react/dist/ssr'

import { DEFAULT_REASON_ID, type ReturnReason } from '@/src/model/return-flow'
import { Button } from './button'
import { ChoiceRow, Heading, Notice } from './primitives'

/**
 * Frame 04 — why the item is going back.
 *
 * The suggestion is pre-selected, and the screen says why in one line. That is
 * the whole design: a guess the user can see the basis of and overrule in one
 * tap, rather than a guess presented as a decision already made.
 */
export function ReasonPicker({
  reasons,
  selectedId,
  onSelect,
  onContinue,
  onSkip,
}: {
  reasons: ReturnReason[]
  selectedId: string | null
  onSelect: (id: string) => void
  onContinue: () => void
  onSkip: () => void
}) {
  const fallback = reasons.find((reason) => reason.id === DEFAULT_REASON_ID)

  return (
    <>
      <Heading
        title="Why is it going back?"
        body="Pre-picked from the item type and how you have returned coats before."
      />

      <ul className="flex flex-col gap-2">
        {reasons.map((reason) => (
          <ChoiceRow
            key={reason.id}
            selected={reason.id === selectedId}
            onSelect={() => onSelect(reason.id)}
            label={reason.label}
            description={reason.id === selectedId ? reason.note : undefined}
          />
        ))}
      </ul>

      <div className="flex flex-col gap-2.5">
        <Button onClick={onContinue} disabled={selectedId === null}>
          Continue
        </Button>
        <Button variant="ghost" onClick={onSkip}>
          Skip — use the default
        </Button>
      </div>

      {/* The footnote names the fallback, so it reads from the same constant
          the skip button uses rather than repeating the label by hand. */}
      <Notice tone="quiet" icon={<InfoIcon size={13} />}>
        Skipping sends “{fallback?.label ?? 'the retailer default'}”, the reason retailers treat
        most neutrally.
      </Notice>
    </>
  )
}
