/**
 * The closed vocabularies from design/boomerang-data-model.md §4.
 *
 * These are closed for API v1: §4 requires that an unknown value fail
 * validation rather than be quietly mapped onto a familiar one, which is why
 * each vocabulary ships with its guard instead of being a bare union type.
 *
 * Mirrors server/app/models/domain.py. When that file's enums change, this one
 * changes with it — the vocabulary is one contract with two implementations,
 * not two vocabularies that happen to agree today.
 */

function memberOf<const T extends readonly string[]>(values: T) {
  return (value: unknown): value is T[number] =>
    typeof value === 'string' && (values as readonly string[]).includes(value)
}

export const RETURN_STATES = [
  'not_started',
  'in_progress',
  'qr_ready',
  'label_ready',
  'handed_to_carrier',
  'complete',
] as const
export type ReturnState = (typeof RETURN_STATES)[number]
export const isReturnState = memberOf(RETURN_STATES)

/**
 * States the extension may name but must never write. §4.1: `handed_to_carrier`
 * is blocked on ARCH-B3 (which component may publish it) and `complete` on
 * ARCH-B8 (what it even means). They are in the vocabulary so the UI can render
 * a summary the server sent; they are listed here so no local code path
 * publishes one by accident before those decisions land.
 */
export const UNWRITABLE_RETURN_STATES = ['handed_to_carrier', 'complete'] as const
export type UnwritableReturnState = (typeof UNWRITABLE_RETURN_STATES)[number]
export const isUnwritableReturnState = memberOf(UNWRITABLE_RETURN_STATES)

export const PREFERENCES = [
  'lowest_cost',
  'fastest_refund_or_replacement',
  'no_printer',
  'more_sustainable',
] as const
export type Preference = (typeof PREFERENCES)[number]
export const isPreference = memberOf(PREFERENCES)

export const POLICY_ELIGIBILITIES = ['eligible', 'ineligible', 'unknown'] as const
export type PolicyEligibility = (typeof POLICY_ELIGIBILITIES)[number]
export const isPolicyEligibility = memberOf(POLICY_ELIGIBILITIES)

export const FACT_ORIGINS = ['retailer_stated', 'derived', 'user_confirmed'] as const
export type FactOrigin = (typeof FACT_ORIGINS)[number]
export const isFactOrigin = memberOf(FACT_ORIGINS)

export const RETURN_SUMMARY_UPDATE_SOURCES = [
  'system_initialization',
  'extension_live_page',
  'user_confirmed',
] as const
export type ReturnSummaryUpdateSource = (typeof RETURN_SUMMARY_UPDATE_SOURCES)[number]
export const isReturnSummaryUpdateSource = memberOf(RETURN_SUMMARY_UPDATE_SOURCES)

/**
 * The only source the extension is entitled to claim. `system_initialization`
 * belongs to the server (§4.5) and `user_confirmed` describes a person, not a
 * page reading.
 */
export const EXTENSION_UPDATE_SOURCE: ReturnSummaryUpdateSource = 'extension_live_page'

export const HANDOFF_EVIDENCE = ['user_confirmed', 'retailer_observed'] as const
export type HandoffEvidence = (typeof HANDOFF_EVIDENCE)[number]
export const isHandoffEvidence = memberOf(HANDOFF_EVIDENCE)

export const URGENCY_LEVELS = ['expired', 'critical', 'soon', 'later', 'unknown'] as const
export type UrgencyLevel = (typeof URGENCY_LEVELS)[number]
export const isUrgencyLevel = memberOf(URGENCY_LEVELS)

/** §8 `WorkflowSession.run_status`. Extension-local; it has no server analogue. */
export const RUN_STATUSES = ['active', 'awaiting_user', 'manual_handoff', 'terminal'] as const
export type RunStatus = (typeof RUN_STATUSES)[number]
export const isRunStatus = memberOf(RUN_STATUSES)
