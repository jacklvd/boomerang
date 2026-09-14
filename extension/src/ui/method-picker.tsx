import { LockSimpleIcon } from '@phosphor-icons/react/dist/ssr'

import { formatMoney } from '@/src/model/read-order'
import { isPaid, type ReturnMethodOption } from '@/src/model/return-flow'
import { Button } from './button'
import { ChoiceRow, Heading, Notice } from './primitives'

/**
 * Frame 06 — how the item goes back.
 *
 * Ranked, with every price visible. The rule the screen exists to keep is that
 * a paid option is never selected for the user: `initialSelection` skips any
 * option that costs money, whatever the ranking says, and the footnote states
 * it so the behaviour is checkable from the screen itself.
 */
export function MethodPicker({
  options,
  selectedId,
  onSelect,
  onContinue,
  title = 'How should it go back?',
  body = "Ranked against your preference for no printer. Prices are the retailer's.",
  /** Frame I1: the method the user is replacing, marked so it is not re-picked
   *  by accident. Its own row says so rather than a legend elsewhere. */
  previouslyChosenId,
}: {
  options: ReturnMethodOption[]
  selectedId: string | null
  onSelect: (methodId: string) => void
  onContinue: () => void
  title?: string
  body?: string
  previouslyChosenId?: string
}) {
  const paid = options.filter(isPaid)
  const selected = options.find((option) => option.methodId === selectedId)

  return (
    <>
      <Heading title={title} body={body} />

      <ul className="flex flex-col gap-2">
        {options.map((option) => (
          <ChoiceRow
            key={option.methodId}
            selected={option.methodId === selectedId}
            onSelect={() => onSelect(option.methodId)}
            label={option.label}
            description={option.description}
            badge={
              option.methodId === previouslyChosenId
                ? 'Previously chosen'
                : option.recommendedBecause
            }
            trailing={<Price option={option} />}
          />
        ))}
      </ul>

      <Button onClick={onContinue} disabled={!selected}>
        {/* The label is the retailer's own, so it is used verbatim. Lowercasing
            it to fit the sentence turned "QR code drop-off" into "qr code
            drop-off" — English casing rules do not survive contact with a
            string someone else chose. */}
        {selected ? `Use ${selected.label}` : 'Choose a method'}
      </Button>

      {paid.length > 0 && (
        <Notice tone="quiet" icon={<LockSimpleIcon size={13} className="text-calm" />}>
          We never select a paid option for you.{' '}
          {paid.map((option) => option.label).join(' and ')} stays unticked unless you tick it.
        </Notice>
      )}
    </>
  )
}

/** §3.4: unknown is not free, and free is not unknown. Three states, not two. */
function Price({ option }: { option: ReturnMethodOption }) {
  if (option.price === null) {
    return <span className="text-[12.5px] text-ink-faint italic">Price not shown</span>
  }
  const free = option.price.amount_minor === 0
  return (
    <span className={free ? 'text-[12.5px] font-semibold text-calm' : 'text-[12.5px] font-semibold text-urgent'}>
      {free ? 'Free' : formatMoney(option.price)}
    </span>
  )
}
