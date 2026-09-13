/**
 * `WorkflowSession` — the extension-local workflow record, design/boomerang-data-model.md §8.
 *
 * This is the one model layer the extension owns outright. Orders, policies and
 * dashboard summaries stay server-authoritative (§2); caching an API response
 * does not make the extension authoritative for it, so none of those shapes are
 * redeclared here.
 *
 * The parser exists because chrome.storage is a trust boundary, not a variable.
 * What comes back out of it was written by an older build, possibly a different
 * schema, possibly a half-finished write, and the MV3 worker that reads it has
 * no memory of writing it. Everything past `parseWorkflowSession` is trusted;
 * nothing before it is.
 */
import {
  isRunStatus,
  type RunStatus,
} from './vocabulary'

/** §3.5: versions an extension-local record shape. §8: starts at 1. */
export const WORKFLOW_SCHEMA_VERSION = 1

/** §3.3. Integer minor units; floating-point amounts are prohibited. */
export type Money = {
  amount_minor: number
  currency: string
}

export type SafeCheckpoint = {
  /** In-memory only, for the active run. Nothing resolves it after a restart. */
  observation_id: string
  retailer_step: string
  url: string
  completed_action_count: number
  recorded_at: string
}

/** §8: field names only. It never contains the value entered. */
export type FilledField = {
  semantic_name: string
  filled_at: string
}

export type SelectedReturnMethod = {
  method_id: string
  label: string
  /** `null` means unknown, not free (§3.4). */
  price: Money | null
  selected_at: string
}

export type WorkflowSession = {
  schema_version: number
  id: string
  account_id: string
  order_id: string
  item_id: string
  run_status: RunStatus
  retailer_step: string
  tab_id: number
  /** Retailer page URL. §8: never synced to the server. */
  last_validated_url: string
  safe_checkpoint: SafeCheckpoint | null
  fields_filled: FilledField[]
  suggested_reason: string | null
  user_confirmed_reason: string | null
  selected_return_method: SelectedReturnMethod | null
  attempt_count: number
  started_at: string
  updated_at: string
}

export type ParseResult<T> = { ok: true; value: T } | { ok: false; reason: string }

class Invalid extends Error {}

function fail(path: string, why: string): never {
  throw new Invalid(`${path} ${why}`)
}

/**
 * Exact key match in both directions, mirroring the server's `extra="forbid"`.
 *
 * Rejecting unknown keys is not pedantry here: it is what keeps §8's redaction
 * rules enforceable. A `FilledField` that arrives carrying a `value` key is a
 * submitted value that reached disk, and the only place left to catch it is the
 * read. Silently dropping the key would let the leak persist in storage.
 */
function record(value: unknown, path: string, keys: readonly string[]): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    fail(path, 'must be an object')
  }
  const actual = Object.keys(value)
  const missing = keys.filter((key) => !actual.includes(key))
  const extra = actual.filter((key) => !keys.includes(key))
  if (missing.length > 0) fail(path, `is missing ${missing.join(', ')}`)
  if (extra.length > 0) fail(path, `has unexpected ${extra.join(', ')}`)
  return value as Record<string, unknown>
}

function text(value: unknown, path: string): string {
  if (typeof value !== 'string' || value.length === 0) fail(path, 'must be a non-empty string')
  return value
}

function integer(value: unknown, path: string, min: number): number {
  if (!Number.isInteger(value)) fail(path, 'must be an integer')
  if ((value as number) < min) fail(path, `must be at least ${min}`)
  return value as number
}

/**
 * §3.2 calls a timestamp an RFC 3339 *UTC* instant. Local records are written
 * by us, so we require the `Z` form rather than accepting an offset and
 * normalizing — two spellings of one instant would make stored records
 * compare unequal for no reason.
 */
const UTC_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$/

function timestamp(value: unknown, path: string): string {
  const raw = text(value, path)
  if (!UTC_TIMESTAMP.test(raw) || Number.isNaN(Date.parse(raw))) {
    fail(path, 'must be an RFC 3339 UTC timestamp')
  }
  return raw
}

/**
 * A stored URL is later navigated to or compared against the active tab, so a
 * `javascript:` or `data:` string surviving a round-trip through storage would
 * be an injection vector with a persistence layer attached.
 */
function pageUrl(value: unknown, path: string): string {
  const raw = text(value, path)
  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    fail(path, 'must be an absolute URL')
  }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    fail(path, 'must be an http(s) URL')
  }
  return raw
}

function nullable<T>(
  value: unknown,
  path: string,
  parse: (value: unknown, path: string) => T,
): T | null {
  return value === null ? null : parse(value, path)
}

function money(value: unknown, path: string): Money {
  const raw = record(value, path, ['amount_minor', 'currency'])
  const currency = text(raw.currency, `${path}.currency`)
  if (!/^[A-Z]{3}$/.test(currency)) fail(`${path}.currency`, 'must be an ISO 4217 code')
  return {
    amount_minor: integer(raw.amount_minor, `${path}.amount_minor`, 0),
    currency,
  }
}

function safeCheckpoint(value: unknown, path: string): SafeCheckpoint {
  const raw = record(value, path, [
    'observation_id',
    'retailer_step',
    'url',
    'completed_action_count',
    'recorded_at',
  ])
  return {
    observation_id: text(raw.observation_id, `${path}.observation_id`),
    retailer_step: text(raw.retailer_step, `${path}.retailer_step`),
    url: pageUrl(raw.url, `${path}.url`),
    completed_action_count: integer(raw.completed_action_count, `${path}.completed_action_count`, 0),
    recorded_at: timestamp(raw.recorded_at, `${path}.recorded_at`),
  }
}

function filledField(value: unknown, path: string): FilledField {
  const raw = record(value, path, ['semantic_name', 'filled_at'])
  return {
    semantic_name: text(raw.semantic_name, `${path}.semantic_name`),
    filled_at: timestamp(raw.filled_at, `${path}.filled_at`),
  }
}

function selectedReturnMethod(value: unknown, path: string): SelectedReturnMethod {
  const raw = record(value, path, ['method_id', 'label', 'price', 'selected_at'])
  return {
    method_id: text(raw.method_id, `${path}.method_id`),
    label: text(raw.label, `${path}.label`),
    price: nullable(raw.price, `${path}.price`, money),
    selected_at: timestamp(raw.selected_at, `${path}.selected_at`),
  }
}

const SESSION_KEYS = [
  'schema_version',
  'id',
  'account_id',
  'order_id',
  'item_id',
  'run_status',
  'retailer_step',
  'tab_id',
  'last_validated_url',
  'safe_checkpoint',
  'fields_filled',
  'suggested_reason',
  'user_confirmed_reason',
  'selected_return_method',
  'attempt_count',
  'started_at',
  'updated_at',
] as const

/**
 * Parses one stored record. Returns a reason instead of throwing: a stale or
 * corrupt session is an expected read outcome, and the caller's answer is to
 * drop it and start clean, not to unwind the worker.
 *
 * Every field is required even when nullable, matching §6's "Required: yes"
 * columns. An absent key and an explicit `null` mean different things — one is
 * a malformed record, the other is a known-unknown fact (§3.4).
 */
export function parseWorkflowSession(value: unknown): ParseResult<WorkflowSession> {
  try {
    const raw = record(value, 'session', SESSION_KEYS)

    /* dev-note: no migration path. v1 is the only shape that has ever shipped,
       so anything else is a record we cannot reason about — a future version
       written by a newer build the user is rolling back from, or a corrupt
       read. Discarding it costs one in-progress run; guessing at it corrupts a
       return. Add a migrator here when there is a v2 to migrate from. */
    if (raw.schema_version !== WORKFLOW_SCHEMA_VERSION) {
      fail('session.schema_version', `must be ${WORKFLOW_SCHEMA_VERSION}`)
    }
    if (!isRunStatus(raw.run_status)) {
      fail('session.run_status', 'must be a known run status')
    }
    if (!Array.isArray(raw.fields_filled)) {
      fail('session.fields_filled', 'must be an array')
    }

    return {
      ok: true,
      value: {
        schema_version: WORKFLOW_SCHEMA_VERSION,
        id: text(raw.id, 'session.id'),
        account_id: text(raw.account_id, 'session.account_id'),
        order_id: text(raw.order_id, 'session.order_id'),
        item_id: text(raw.item_id, 'session.item_id'),
        run_status: raw.run_status,
        retailer_step: text(raw.retailer_step, 'session.retailer_step'),
        tab_id: integer(raw.tab_id, 'session.tab_id', 0),
        last_validated_url: pageUrl(raw.last_validated_url, 'session.last_validated_url'),
        safe_checkpoint: nullable(raw.safe_checkpoint, 'session.safe_checkpoint', safeCheckpoint),
        fields_filled: raw.fields_filled.map((field, index) =>
          filledField(field, `session.fields_filled[${index}]`),
        ),
        suggested_reason: nullable(raw.suggested_reason, 'session.suggested_reason', text),
        user_confirmed_reason: nullable(
          raw.user_confirmed_reason,
          'session.user_confirmed_reason',
          text,
        ),
        selected_return_method: nullable(
          raw.selected_return_method,
          'session.selected_return_method',
          selectedReturnMethod,
        ),
        attempt_count: integer(raw.attempt_count, 'session.attempt_count', 0),
        started_at: timestamp(raw.started_at, 'session.started_at'),
        updated_at: timestamp(raw.updated_at, 'session.updated_at'),
      },
    }
  } catch (error) {
    if (error instanceof Invalid) return { ok: false, reason: error.message }
    throw error
  }
}
