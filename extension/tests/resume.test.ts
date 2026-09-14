import { describe, expect, it } from 'vitest'

import { formatSavedAt, resumeView } from '../src/model/resume'
import { permittedFields, FIXTURE_MANUAL_FIELDS, PERMITTED_KINDS } from '../src/model/manual-entry'
import { WORKFLOW_SCHEMA_VERSION, type WorkflowSession } from '../src/model/workflow'

const session = (overrides: Partial<WorkflowSession> = {}): WorkflowSession => ({
  schema_version: WORKFLOW_SCHEMA_VERSION,
  id: 'wfs_1',
  account_id: 'acct_1',
  order_id: 'order_1',
  item_id: 'item_1',
  run_status: 'awaiting_user',
  retailer_step: 'select_method',
  tab_id: 42,
  last_validated_url: 'https://retailer.example/returns',
  safe_checkpoint: null,
  fields_filled: [],
  suggested_reason: 'too_small',
  user_confirmed_reason: 'Too small',
  selected_return_method: null,
  attempt_count: 1,
  started_at: '2026-09-03T21:14:00Z',
  updated_at: '2026-09-03T21:14:00Z',
  ...overrides,
})

const at = (iso: string) => new Date(`${iso}T12:00:00`)

describe('the deadline is recomputed, never restored', () => {
  /* The screen promises "re-checked against today's date, not the one saved
     with the draft". A draft can sit for days, so every time-dependent fact in
     it is stale the moment it is written. */
  it('counts from today, so the same draft reads differently later', () => {
    const view = (today: string) =>
      resumeView(session(), { returnBy: '2026-09-17', tabIsLive: true, now: at(today) })

    expect(view('2026-09-15').daysRemaining).toBe(2)
    expect(view('2026-09-05').daysRemaining).toBe(12)
  })

  it('goes expired once the window closed while the draft sat', () => {
    const view = resumeView(session(), {
      returnBy: '2026-09-10',
      tabIsLive: true,
      now: at('2026-09-14'),
    })
    expect(view.expired).toBe(true)
    expect(view.daysRemaining).toBe(-4)
  })

  /* §3.4: an unknown fact is not filled in with a guess, and an absent
     deadline must not read as "there is still time". */
  it('reports no deadline rather than inventing one', () => {
    const view = resumeView(session(), { returnBy: null, tabIsLive: true, now: at('2026-09-14') })
    expect(view.daysRemaining).toBeNull()
    expect(view.expired).toBe(false)
  })
})

describe('steps come from the draft, not from a stored cursor', () => {
  it('marks the first unfinished step current and the rest pending', () => {
    const view = resumeView(session(), { returnBy: null, tabIsLive: true })
    expect(view.steps.map((step) => step.state)).toEqual(['done', 'done', 'current', 'pending'])
    expect(view.steps[1]!.label).toBe('Reason set to “Too small”')
    expect(view.steps[2]!.label).toBe('Return method — not chosen')
  })

  it('moves the cursor when the draft holds more', () => {
    const view = resumeView(
      session({
        selected_return_method: {
          method_id: 'qr_dropoff',
          label: 'QR code drop-off',
          price: { amount_minor: 0, currency: 'USD' },
          selected_at: '2026-09-03T21:13:00Z',
        },
      }),
      { returnBy: null, tabIsLive: true },
    )
    expect(view.steps.map((step) => step.state)).toEqual(['done', 'done', 'done', 'current'])
    expect(view.steps[2]!.label).toBe('Return method — QR code drop-off')
  })

  it('falls back when the reason was never confirmed', () => {
    const view = resumeView(session({ user_confirmed_reason: null }), {
      returnBy: null,
      tabIsLive: true,
    })
    expect(view.steps[1]!.state).toBe('current')
    expect(view.steps[1]!.label).toBe('Reason — not chosen')
  })
})

describe('resumability', () => {
  /* §8: `awaiting_user` "does not promise pause/resume across tab closure".
     The button reports that rather than pretending it can drive a dead tab. */
  it('cannot resume into a tab that is gone', () => {
    expect(resumeView(session(), { returnBy: null, tabIsLive: false }).resumable).toBe(false)
  })

  it('cannot resume a terminal run', () => {
    const view = resumeView(session({ run_status: 'terminal' }), {
      returnBy: null,
      tabIsLive: true,
    })
    expect(view.resumable).toBe(false)
  })

  it('resumes a live awaiting_user run', () => {
    expect(resumeView(session(), { returnBy: null, tabIsLive: true }).resumable).toBe(true)
  })
})

describe('formatSavedAt', () => {
  it('survives a malformed timestamp rather than rendering Invalid Date', () => {
    expect(formatSavedAt('not a date')).toBe('an unknown time')
  })
})

describe('the manual form refuses fields it must not render', () => {
  /* Frame I2 promises password, payment and file-upload fields are excluded
     "manually or not". This is the one path where the agent's closed action
     vocabulary is not standing between a page and a keystroke, so the promise
     has to be enforced somewhere other than the copy. */
  it('drops anything outside the allowlist and names it', () => {
    const { allowed, refused } = permittedFields([
      { name: 'reason', kind: 'choice' },
      { name: 'card_number', kind: 'payment' },
      { name: 'account_password', kind: 'password' },
      { name: 'receipt', kind: 'file' },
      { name: 'note', kind: 'long-text' },
    ])
    expect(allowed).toEqual(['reason', 'note'])
    expect(refused).toEqual(['card_number', 'account_password', 'receipt'])
  })

  /* An allowlist, not a denylist: a denylist has to anticipate every spelling
     a retailer might use for a card field. */
  it('refuses an unfamiliar kind rather than assuming it is safe', () => {
    const { allowed, refused } = permittedFields([{ name: 'mystery', kind: 'signature-pad' }])
    expect(allowed).toEqual([])
    expect(refused).toEqual(['mystery'])
  })

  it('ships only permitted kinds', () => {
    for (const field of FIXTURE_MANUAL_FIELDS) {
      expect(PERMITTED_KINDS, field.name).toContain(field.kind)
    }
  })
})
