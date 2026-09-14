/**
 * The choices a return run puts to the user: why it is going back, and how.
 *
 * Both are **local**. §8 types `suggested_reason` and `user_confirmed_reason`
 * as plain strings and calls them a "local suggestion" and a "local
 * user-confirmed choice", and `SelectedReturnMethod.method_id` is explicitly
 * "retailer-session-local". Neither has a closed vocabulary, because both come
 * from whatever the retailer's own form offers.
 *
 * So these types describe what the popup renders, not a wire contract — the
 * same footing as `ReadOrder`.
 */
import type { Money } from './workflow'

export type ReturnReason = {
  /** What gets written to `user_confirmed_reason`. The retailer's own value. */
  id: string
  label: string
  /** Why this one was pre-picked. Shown only on the suggestion. */
  note?: string
}

export type ReturnMethodOption = {
  /** §8 `SelectedReturnMethod.method_id`. */
  methodId: string
  label: string
  description: string
  /** §3.4: `null` means unknown, not free. Zero means free. */
  price: Money | null
  /** Set on at most one option, and only when a preference explains it. */
  recommendedBecause?: string
}

export function isPaid(option: ReturnMethodOption): boolean {
  return option.price !== null && option.price.amount_minor > 0
}

/**
 * The option to pre-select, or null.
 *
 * Never a paid one — that is the promise the footnote makes, and leaving it to
 * the ranking would break it the first time a paid option ranked first. An
 * unknown price is also skipped: it may turn out to cost money, and a default
 * the user has to undo is worse than no default.
 */
export function initialSelection(options: ReturnMethodOption[]): string | null {
  const free = options.find((option) => option.price !== null && option.price.amount_minor === 0)
  return free?.methodId ?? null
}

/**
 * §8 requires `selected_at` to follow an explicit user choice, so the selection
 * is only ever built here — never defaulted from the ranking.
 */
export function confirmMethod(option: ReturnMethodOption, now: Date) {
  return {
    method_id: option.methodId,
    label: option.label,
    price: option.price,
    selected_at: now.toISOString().replace(/\.\d+Z$/, 'Z'),
  }
}

/** What the review screen restates before anything is sent. */
export type ReviewSummary = {
  items: string
  reason: string | null
  method: string | null
  refundTo: string
}

/* dev-note: fixtures for the preview. The real lists come off the retailer's
   own form, which needs the extractor. */
export const FIXTURE_REASONS: ReturnReason[] = [
  { id: 'too_small', label: 'Too small', note: 'Most common reason for outerwear' },
  { id: 'changed_mind', label: 'Changed my mind' },
  { id: 'damaged', label: 'Arrived damaged' },
  { id: 'not_as_described', label: 'Not as described' },
  { id: 'wrong_item', label: 'Wrong item sent' },
]

/**
 * §8: the fallback when the user skips. Named here rather than inlined in the
 * component because the footnote promises which one it is, and the promise and
 * the behaviour have to come from the same place.
 */
export const DEFAULT_REASON_ID = 'changed_mind'

export const FIXTURE_METHODS: ReturnMethodOption[] = [
  {
    methodId: 'qr_dropoff',
    label: 'QR code drop-off',
    description: 'No printer needed. Nearest drop-off: Walgreens, 0.4 mi.',
    price: { amount_minor: 0, currency: 'USD' },
    recommendedBecause: 'Matches your preference for no printer',
  },
  {
    methodId: 'in_store',
    label: 'Return in store',
    description: 'Nordstrom, Pioneer Place — 1.2 mi.',
    price: { amount_minor: 0, currency: 'USD' },
  },
  {
    methodId: 'prepaid_label',
    label: 'Prepaid label by mail',
    description: 'Print it yourself, then hand it to any carrier counter.',
    price: { amount_minor: 0, currency: 'USD' },
  },
  {
    methodId: 'home_collection',
    label: 'Home collection',
    description: 'Nordstrom arranges it. Deducted from your refund.',
    price: { amount_minor: 699, currency: 'USD' },
  },
]
