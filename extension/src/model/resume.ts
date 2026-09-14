/**
 * Rebuilding an interrupted run from what survived in local storage.
 *
 * The design's promise on frame I3 is the whole of this file: "re-checked
 * against today's date, not the one saved with the draft". A draft can sit for
 * days, and every time-dependent fact in it is stale the moment it is written.
 * So nothing here trusts a derived value off the session — the session carries
 * what the user chose, and everything downstream of the clock is recomputed.
 */
import { daysUntil } from './read-order'
import type { WorkflowSession } from './workflow'

export type StepState = 'done' | 'current' | 'pending'

export type ResumeStep = {
  label: string
  state: StepState
}

export type ResumeView = {
  steps: ResumeStep[]
  /** Null when there is no known deadline, never a guess. */
  daysRemaining: number | null
  /** True once the window has closed while the draft sat. */
  expired: boolean
  /**
   * Whether "Continue from here" can do anything. A run whose tab is gone
   * cannot be resumed into, and offering it would be a dead button.
   */
  resumable: boolean
}

/**
 * The four steps frame I3 shows, derived from what the session actually holds.
 *
 * `current` is the first thing not yet done rather than a stored cursor.
 * Storing which step you were on invites the stored cursor and the stored data
 * to disagree, and then the screen tells the user something the draft does not
 * support.
 */
export function resumeView(
  session: WorkflowSession,
  options: { returnBy: string | null; tabIsLive: boolean; now?: Date },
): ResumeView {
  const { returnBy, tabIsLive, now = new Date() } = options

  const done = [
    { label: 'Order read and normalised', done: true },
    {
      label: session.user_confirmed_reason
        ? `Reason set to “${session.user_confirmed_reason}”`
        : 'Reason — not chosen',
      done: session.user_confirmed_reason !== null,
    },
    {
      label: session.selected_return_method
        ? `Return method — ${session.selected_return_method.label}`
        : 'Return method — not chosen',
      done: session.selected_return_method !== null,
    },
    { label: 'Review and submit', done: false },
  ]

  const firstUnfinished = done.findIndex((step) => !step.done)
  const steps: ResumeStep[] = done.map((step, index) => ({
    label: step.label,
    state: step.done ? 'done' : index === firstUnfinished ? 'current' : 'pending',
  }))

  /* Recomputed from today, never read off the draft. */
  const daysRemaining = returnBy === null ? null : daysUntil(returnBy, now)

  return {
    steps,
    daysRemaining,
    expired: daysRemaining !== null && daysRemaining < 0,
    /* A terminal run has nowhere to go, and a dead tab has nothing to drive.
       §8 is explicit that `awaiting_user` "does not promise pause/resume across
       tab closure", so this reports the fact rather than pretending. */
    resumable: tabIsLive && session.run_status !== 'terminal',
  }
}

/** `3 September, 9:14pm` — when the draft was last written. */
export function formatSavedAt(isoTimestamp: string): string {
  const date = new Date(isoTimestamp)
  if (Number.isNaN(date.getTime())) return 'an unknown time'
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'long',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date)
}
