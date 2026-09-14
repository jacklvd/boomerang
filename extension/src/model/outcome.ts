/**
 * What a finished run produced, split by what may be kept.
 *
 * The split is the point of the file. `RETURN_WORKFLOW.md` lists a raw label
 * or QR artifact under "never persisted", and the retention baseline gives it
 * zero durable retention; for a QR outcome the server stores only the
 * `qr_ready` status. So the two halves are separate types rather than optional
 * fields on one, and only one of them has a name that sounds storable.
 *
 * dev-note: the terminal-page handling that *produces* these is not built.
 * Issue #34 is open on the terminal-page sanitizer, and building extraction
 * here first would reach for the ingestion guard by default — which is the
 * thing that issue exists to prevent. These types describe what the screen
 * renders from a page already on screen.
 */
import type { ReturnState } from './vocabulary'

/** The only outcomes `report_outcome` may report in v1. */
export const TERMINAL_OUTCOMES = ['qr_ready', 'label_ready'] as const
export type TerminalOutcome = (typeof TERMINAL_OUTCOMES)[number]

export function isTerminalOutcome(value: unknown): value is TerminalOutcome {
  return typeof value === 'string' && (TERMINAL_OUTCOMES as readonly string[]).includes(value)
}

/**
 * The half that may cross into storage: a state, and nothing else.
 *
 * `ReturnState` is the shared vocabulary, so this is what a `ReturnSummary`
 * write would carry. Anything the retailer drew stays out of it by
 * construction.
 */
export type DurableOutcome = {
  state: Extract<ReturnState, 'qr_ready' | 'label_ready'>
  observedAt: string
}

/**
 * The half that must not. Rendered from the page in front of the user and
 * dropped when the popup closes.
 *
 * `artifactAltText` is the accessible description of the code, not the code —
 * there is nowhere here to put the QR's payload, and that is deliberate.
 */
export type EphemeralOutcome = {
  /** Retailer's own reference. Shown so the user can quote it; not an artifact. */
  reference: string | null
  artifactAltText: string
  dropOff: { name: string; distance: string; note: string } | null
  /** ISO date the retailer stated for the drop-off, if it stated one. */
  dropOffBy: string | null
}

export function durableFrom(outcome: TerminalOutcome, now: Date): DurableOutcome {
  return { state: outcome, observedAt: now.toISOString().replace(/\.\d+Z$/, 'Z') }
}

/**
 * What the popup is allowed to hand upward.
 *
 * Takes the whole outcome and returns only the durable half, so a caller that
 * wants to publish a summary cannot accidentally pass the rest along. The test
 * asserts the result contains no ephemeral field.
 */
export function publishable(
  outcome: TerminalOutcome,
  _ephemeral: EphemeralOutcome,
  now: Date,
): DurableOutcome {
  return durableFrom(outcome, now)
}

/* dev-note: preview only. */
export const FIXTURE_EPHEMERAL: EphemeralOutcome = {
  reference: 'RMA 8842-QK21',
  artifactAltText: 'QR code issued by Nordstrom for this return',
  dropOff: { name: 'Walgreens', distance: '0.4 mi', note: 'Open until 10pm' },
  dropOffBy: '2026-09-17',
}
