import { describe, expect, it } from 'vitest'

import {
  parseWorkflowSession,
  WORKFLOW_SCHEMA_VERSION,
  type WorkflowSession,
} from '../src/model/workflow'
import {
  EXTENSION_UPDATE_SOURCE,
  isReturnState,
  isReturnSummaryUpdateSource,
  isRunStatus,
  isUnwritableReturnState,
  RETURN_STATES,
} from '../src/model/vocabulary'

/** A minimal valid record. Tests mutate a clone rather than restating it. */
const VALID: WorkflowSession = {
  schema_version: WORKFLOW_SCHEMA_VERSION,
  id: 'wfs_01',
  account_id: 'acct_01',
  order_id: 'order_01',
  item_id: 'item_01',
  run_status: 'active',
  retailer_step: 'select_items',
  tab_id: 42,
  last_validated_url: 'https://retailer.example/returns/start',
  safe_checkpoint: null,
  fields_filled: [],
  suggested_reason: null,
  user_confirmed_reason: null,
  selected_return_method: null,
  attempt_count: 0,
  started_at: '2026-09-01T20:03:00Z',
  updated_at: '2026-09-01T20:03:00Z',
}

const withField = (patch: Record<string, unknown>): unknown => ({ ...VALID, ...patch })

const reasonFor = (value: unknown): string => {
  const result = parseWorkflowSession(value)
  if (result.ok) throw new Error('expected the record to be rejected')
  return result.reason
}

describe('closed vocabularies', () => {
  it('matches the six server return states in order', () => {
    expect([...RETURN_STATES]).toEqual([
      'not_started',
      'in_progress',
      'qr_ready',
      'label_ready',
      'handed_to_carrier',
      'complete',
    ])
  })

  it('rejects a value outside the vocabulary rather than mapping it', () => {
    expect(isReturnState('in_progress')).toBe(true)
    expect(isReturnState('shipped')).toBe(false)
    expect(isReturnState('IN_PROGRESS')).toBe(false)
    expect(isReturnState(undefined)).toBe(false)
  })

  it('names the two states blocked on ARCH-B3 and ARCH-B8', () => {
    expect(isUnwritableReturnState('handed_to_carrier')).toBe(true)
    expect(isUnwritableReturnState('complete')).toBe(true)
    expect(isUnwritableReturnState('qr_ready')).toBe(false)
  })

  it('claims only the update source the extension is entitled to', () => {
    expect(EXTENSION_UPDATE_SOURCE).toBe('extension_live_page')
    expect(isReturnSummaryUpdateSource(EXTENSION_UPDATE_SOURCE)).toBe(true)
  })

  it('keeps run status extension-local and distinct from return state', () => {
    expect(isRunStatus('awaiting_user')).toBe(true)
    expect(isRunStatus('in_progress')).toBe(false)
  })
})

describe('parseWorkflowSession', () => {
  it('accepts a minimal valid record unchanged', () => {
    const result = parseWorkflowSession(structuredClone(VALID))
    expect(result).toEqual({ ok: true, value: VALID })
  })

  it('accepts a fully populated record', () => {
    const full: WorkflowSession = {
      ...VALID,
      run_status: 'awaiting_user',
      safe_checkpoint: {
        observation_id: 'obs_01',
        retailer_step: 'select_items',
        url: 'https://retailer.example/returns/items',
        completed_action_count: 3,
        recorded_at: '2026-09-01T20:04:11.250Z',
      },
      fields_filled: [{ semantic_name: 'return_reason', filled_at: '2026-09-01T20:04:00Z' }],
      suggested_reason: 'too_small',
      user_confirmed_reason: 'too_small',
      selected_return_method: {
        method_id: 'm_dropoff',
        label: 'Drop off at carrier',
        price: { amount_minor: 0, currency: 'USD' },
        selected_at: '2026-09-01T20:05:00Z',
      },
      attempt_count: 2,
    }
    expect(parseWorkflowSession(structuredClone(full))).toEqual({ ok: true, value: full })
  })

  it('discards a record from another schema version instead of migrating it', () => {
    expect(reasonFor(withField({ schema_version: 2 }))).toContain('schema_version')
  })

  it('rejects an unknown run status', () => {
    expect(reasonFor(withField({ run_status: 'paused' }))).toContain('run_status')
  })

  it('separates a missing key from an explicit null', () => {
    const { suggested_reason: _omitted, ...missing } = VALID
    expect(reasonFor(missing)).toContain('is missing suggested_reason')
    expect(parseWorkflowSession(withField({ suggested_reason: null })).ok).toBe(true)
  })

  it('rejects an unexpected key rather than dropping it', () => {
    expect(reasonFor(withField({ page_html: '<html>' }))).toContain('has unexpected page_html')
  })

  it('rejects a filled field carrying the value that was entered', () => {
    const leaked = withField({
      fields_filled: [
        { semantic_name: 'return_reason', filled_at: '2026-09-01T20:04:00Z', value: 'too small' },
      ],
    })
    expect(reasonFor(leaked)).toContain('has unexpected value')
  })

  it('rejects a non-http URL that reached storage', () => {
    expect(reasonFor(withField({ last_validated_url: 'javascript:alert(1)' }))).toContain(
      'http(s)',
    )
    expect(reasonFor(withField({ last_validated_url: '/returns/start' }))).toContain('absolute')
  })

  it('requires UTC timestamps, not offsets', () => {
    expect(reasonFor(withField({ started_at: '2026-09-01T20:03:00+05:00' }))).toContain('RFC 3339')
    expect(reasonFor(withField({ started_at: '2026-09-01' }))).toContain('RFC 3339')
    expect(parseWorkflowSession(withField({ started_at: '2026-09-01T20:03:00.5Z' })).ok).toBe(true)
  })

  it('rejects a non-integer or negative counter', () => {
    expect(reasonFor(withField({ attempt_count: 1.5 }))).toContain('integer')
    expect(reasonFor(withField({ attempt_count: -1 }))).toContain('at least 0')
    expect(reasonFor(withField({ tab_id: '42' }))).toContain('tab_id')
  })

  it('rejects a floating-point money amount', () => {
    const method = {
      method_id: 'm_1',
      label: 'Mail back',
      price: { amount_minor: 8.99, currency: 'USD' },
      selected_at: '2026-09-01T20:05:00Z',
    }
    expect(reasonFor(withField({ selected_return_method: method }))).toContain('amount_minor')
  })

  it('rejects a malformed currency code', () => {
    const method = {
      method_id: 'm_1',
      label: 'Mail back',
      price: { amount_minor: 899, currency: 'usd' },
      selected_at: '2026-09-01T20:05:00Z',
    }
    expect(reasonFor(withField({ selected_return_method: method }))).toContain('ISO 4217')
  })

  it('names the offending path so a bad read is debuggable', () => {
    const fields = [
      { semantic_name: 'return_reason', filled_at: '2026-09-01T20:04:00Z' },
      { semantic_name: '', filled_at: '2026-09-01T20:04:00Z' },
    ]
    expect(reasonFor(withField({ fields_filled: fields }))).toBe(
      'session.fields_filled[1].semantic_name must be a non-empty string',
    )
  })

  it('rejects the shapes a corrupt storage read actually produces', () => {
    expect(reasonFor(null)).toContain('must be an object')
    expect(reasonFor([])).toContain('must be an object')
    expect(reasonFor('{}')).toContain('must be an object')
    expect(reasonFor(undefined)).toContain('must be an object')
  })
})
