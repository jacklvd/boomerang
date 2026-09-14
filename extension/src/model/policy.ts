/**
 * The retailer's return policy as Boomerang normalized it — data-model §6.4,
 * with the sourced value objects from §5.2 and §5.3.
 *
 * Unlike `ReadOrder`, this shape is not invented: `ReturnPolicy`, `PolicyRule`,
 * `SourcedDate` and `SourcedMoney` are all specified. Where the design and the
 * contract disagree, the contract wins and the gap is noted rather than filled.
 */
import type { FactOrigin, PolicyEligibility } from './vocabulary'
import type { Money } from './workflow'

/** §5.2. `confidence` is normally null for an explicit retailer statement. */
export type SourcedDate = {
  value: string
  origin: FactOrigin
  confidence: number | null
}

/** §5.3. */
export type SourcedMoney = {
  value: Money
  origin: FactOrigin
  confidence: number | null
}

/**
 * §6.4: "a concise normalized fact, not a page-text excerpt".
 *
 * dev-note: there is no `label` field, so a rule cannot be rendered as a
 * `Condition: Unworn, tags attached` pair the way the Pencil frame shows it.
 * The frame's row labels have no source in the contract; they are rendered as
 * plain facts here rather than inventing a key for each. Worth reconciling one
 * way or the other before this ships.
 */
export type PolicyRule = {
  id: string
  text: string
  origin: FactOrigin
  confidence: number | null
}

export type ReturnPolicy = {
  itemId: string
  eligibility: PolicyEligibility
  /** §6.4: the authoritative deadline fact when known. */
  returnBy: SourcedDate | null
  /** §6.4: "`null` does not mean free". Rendered as unknown, never as zero. */
  fee: SourcedMoney | null
  rules: PolicyRule[]
}

/**
 * How a fact should be presented given where it came from.
 *
 * §5.2 carries `origin` precisely so the UI can stop short of asserting a
 * derived guess as the retailer's word. `derived` is the one that has to read
 * differently — it is Boomerang's inference, and saying so is the difference
 * between a prompt and a promise.
 */
export function provenanceNote(origin: FactOrigin): string | null {
  switch (origin) {
    case 'retailer_stated':
      return null
    case 'derived':
      return 'Worked out by Boomerang, not stated by the retailer'
    case 'user_confirmed':
      return 'You confirmed this'
  }
}

/* dev-note: stands in for the parsing pipeline, which is server-side and
   behind a deferred endpoint. Reachable only under PREVIEW. */
export const FIXTURE_POLICY: ReturnPolicy = {
  itemId: 'read_1',
  eligibility: 'eligible',
  returnBy: { value: '2026-09-17', origin: 'retailer_stated', confidence: null },
  fee: null,
  rules: [
    { id: 'r1', text: 'Unworn, with tags attached', origin: 'retailer_stated', confidence: null },
    {
      id: 'r2',
      text: 'QR drop-off, printable label, or in store',
      origin: 'retailer_stated',
      confidence: null,
    },
    { id: 'r3', text: 'Sale items follow the same window', origin: 'derived', confidence: 0.7 },
  ],
}
