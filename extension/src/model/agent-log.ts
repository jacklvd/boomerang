/**
 * The step log the driver screens show, and the rule that keeps it safe.
 *
 * D14 fixes the vocabulary: on each step the agent proposes exactly one tool
 * call from a closed set, and trusted extension code validates it against the
 * live page before executing. The log is the user-facing trace of that.
 *
 * Frame E1's footnote is the constraint: "we keep the step that failed, never
 * the page content". A log line that quoted the page would put retailer text —
 * possibly an address, possibly a value the user typed — into a record the user
 * can screenshot and we might later ship in a bug report. So an entry names
 * *what was done to what kind of thing*, and there is nowhere to put anything
 * else.
 */

/** D14's closed vocabulary. An unknown tool is a protocol error, not a step. */
export const AGENT_TOOLS = [
  'click',
  'select_option',
  'fill',
  'pause_for_user',
  'report_stuck',
  'report_outcome',
] as const
export type AgentTool = (typeof AGENT_TOOLS)[number]

export function isAgentTool(value: unknown): value is AgentTool {
  return typeof value === 'string' && (AGENT_TOOLS as readonly string[]).includes(value)
}

export type StepState = 'done' | 'running' | 'pending' | 'failed'

/**
 * One line of the log.
 *
 * `label` is written by us from the tool and the semantic target — never
 * assembled from page text. There is deliberately no field for a value, a
 * selector, or a quotation.
 */
export type LogEntry = {
  tool: AgentTool
  /** A semantic field name, the same vocabulary `FilledField` uses. */
  target: string
  label: string
  state: StepState
}

const VERB: Record<AgentTool, (target: string) => string> = {
  click: (target) => `Selected ${target}`,
  select_option: (target) => `Set ${target}`,
  fill: (target) => `Filled in ${target}`,
  pause_for_user: () => 'Handed control back to you',
  report_stuck: (target) => `Could not find ${target}`,
  report_outcome: () => 'Reached the retailer’s confirmation',
}

/**
 * Builds a line. The only inputs are the tool and a semantic target, which is
 * what makes "never the page content" structural rather than a habit.
 */
export function logEntry(tool: AgentTool, target: string, state: StepState): LogEntry {
  return { tool, target, label: VERB[tool](target), state }
}

/**
 * Whether a run ended without reaching the retailer's confirmation.
 *
 * `report_stuck` is a terminal outcome in the vocabulary, and E1 exists for it.
 * Treating a stuck run as merely "not finished yet" would leave the user
 * watching a spinner for a run that has already stopped.
 */
export function isStuck(entries: LogEntry[]): boolean {
  return entries.some((entry) => entry.tool === 'report_stuck' && entry.state === 'failed')
}

/* dev-note: the real log comes from the driver, which does not exist. These
   two stand in for a run in progress and a run that stopped.

   The targets are phrased to read with the fixed verb for their tool — "the
   returns link", not "the returns page", because `click` renders as "Selected"
   and nothing may hand-write a label. The Pencil frame says "Opened the returns
   page"; one verb per tool is the price of labels that cannot carry page text. */
export const FIXTURE_RUNNING: LogEntry[] = [
  logEntry('click', 'the returns link', 'done'),
  logEntry('click', 'the overcoat', 'done'),
  logEntry('select_option', 'the reason to “Too small”', 'done'),
  logEntry('select_option', 'the return method', 'running'),
  logEntry('report_outcome', '', 'pending'),
]

export const FIXTURE_STUCK: LogEntry[] = [
  logEntry('click', 'the returns link', 'done'),
  logEntry('click', 'the overcoat', 'done'),
  logEntry('report_stuck', 'the reason field', 'failed'),
]
