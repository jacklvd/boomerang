import {
  CalendarBlankIcon,
  CurrencyDollarIcon,
  TagIcon,
  WarningIcon,
} from '@phosphor-icons/react/dist/ssr'

import { formatDate, formatMoney } from '@/src/model/read-order'
import { provenanceNote, type ReturnPolicy } from '@/src/model/policy'
import { Button } from './button'
import { Fact, Heading, Notice, Panel } from './primitives'

/**
 * Frame 05 — the retailer's rules, as parsed.
 *
 * Two things this screen must not do. It must not present a fee it does not
 * know as free (§6.4: `null` does not mean free), and it must not present a
 * derived guess as the retailer's word (§5.2 carries `origin` for exactly
 * that). Both are handled in the row, not in the copy.
 */
export function PolicySummary({
  retailerName,
  policy,
  onContinue,
  onOpenDashboard,
}: {
  retailerName: string
  policy: ReturnPolicy
  onContinue: () => void
  onOpenDashboard: () => void
}) {
  return (
    <>
      <Heading
        title={`${retailerName}'s return rules`}
        body="Parsed from their policy page for this item category."
      />

      {policy.eligibility === 'ineligible' && (
        <Notice tone="urgent" icon={<WarningIcon size={14} weight="fill" />}>
          {retailerName} does not accept returns on this item. You can still open the flow, but
          expect to finish it yourself.
        </Notice>
      )}

      <Panel>
        <Fact
          icon={<CalendarBlankIcon size={15} />}
          label="Window"
          value={policy.returnBy && formatDate(policy.returnBy.value)}
          note={policy.returnBy && provenanceNote(policy.returnBy.origin)}
        />
        <Fact
          icon={<CurrencyDollarIcon size={15} />}
          label="Return fee"
          value={policy.fee && formatMoney(policy.fee.value)}
          note={policy.fee && provenanceNote(policy.fee.origin)}
        />
        {/* §6.4 gives a rule `text` and no label, so each one is rendered as
            the fact it is. The Pencil frame labels these rows Condition and
            Methods; those labels have no source in the contract. */}
        {policy.rules.map((rule) => (
          <Fact
            key={rule.id}
            icon={<TagIcon size={15} />}
            label="Rule"
            value={rule.text}
            note={provenanceNote(rule.origin)}
          />
        ))}
      </Panel>

      <Notice tone="warn" icon={<WarningIcon size={14} />}>
        Policies vary by category, sale status and membership. Treat this as a prompt to act, not a
        guarantee.
      </Notice>

      <button
        type="button"
        onClick={onOpenDashboard}
        className="w-fit text-[12.5px] font-semibold text-accent hover:underline"
      >
        Full policy on your dashboard
      </button>

      <Button onClick={onContinue}>Continue</Button>
    </>
  )
}
