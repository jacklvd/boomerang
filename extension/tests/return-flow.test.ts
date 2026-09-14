import { describe, expect, it } from 'vitest'

import {
  confirmMethod,
  initialSelection,
  isPaid,
  DEFAULT_REASON_ID,
  FIXTURE_METHODS,
  FIXTURE_REASONS,
} from '../src/model/return-flow'
import { provenanceNote, FIXTURE_POLICY } from '../src/model/policy'

import type { Money } from '../src/model/workflow'
import type { ReturnMethodOption } from '../src/model/return-flow'

const free: Money = { amount_minor: 0, currency: 'USD' }
const paid: Money = { amount_minor: 699, currency: 'USD' }
const option = (methodId: string, price: Money | null): ReturnMethodOption => ({
  methodId,
  label: methodId,
  description: '',
  price,
})

describe('no paid option is ever pre-selected', () => {
  /* The footnote on frame 06 promises this. Leaving it to the ranking would
     break the promise the first time a paid option ranked first. */
  it('skips a paid option even when it ranks first', () => {
    expect(initialSelection([option('courier', paid), option('qr', free)])).toBe('qr')
  })

  /* An unknown price may turn out to cost money, and a default the user has to
     undo is worse than no default. */
  it('skips an unknown price too', () => {
    expect(initialSelection([option('mystery', null), option('qr', free)])).toBe('qr')
  })

  it('selects nothing rather than something that costs money', () => {
    expect(initialSelection([option('courier', paid)])).toBeNull()
    expect(initialSelection([option('mystery', null)])).toBeNull()
    expect(initialSelection([])).toBeNull()
  })

  it('pre-selects the first free option in the shipped fixture', () => {
    expect(initialSelection(FIXTURE_METHODS)).toBe('qr_dropoff')
    expect(isPaid(FIXTURE_METHODS.find((m) => m.methodId === 'qr_dropoff')!)).toBe(false)
  })

  it('counts zero as free and not as paid', () => {
    expect(isPaid(option('qr', free))).toBe(false)
    expect(isPaid(option('courier', paid))).toBe(true)
    expect(isPaid(option('mystery', null))).toBe(false)
  })
})

describe('confirmMethod', () => {
  /* §8: `selected_at` must follow an explicit user choice, and the timestamp
     has to be the UTC form `parseWorkflowSession` accepts. */
  it('records the choice in the shape the session parser will accept', () => {
    const chosen = confirmMethod(FIXTURE_METHODS[0]!, new Date('2026-09-14T06:05:00.123Z'))
    expect(chosen).toEqual({
      method_id: 'qr_dropoff',
      label: 'QR code drop-off',
      price: { amount_minor: 0, currency: 'USD' },
      selected_at: '2026-09-14T06:05:00Z',
    })
    expect(chosen.selected_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/)
  })
})

describe('the skip fallback', () => {
  /* The footnote names the reason skipping sends. It reads from this constant,
     so the promise and the behaviour cannot drift apart. */
  it('names a reason that is actually in the list', () => {
    expect(FIXTURE_REASONS.some((reason) => reason.id === DEFAULT_REASON_ID)).toBe(true)
  })

  it('explains only the suggestion, not every option', () => {
    expect(FIXTURE_REASONS.filter((reason) => reason.note).length).toBe(1)
  })
})

describe('provenance', () => {
  /* §5.2 carries `origin` so the UI can stop short of asserting a guess as the
     retailer's word. A derived fact has to read differently from a stated one. */
  it('says nothing for a retailer-stated fact and flags a derived one', () => {
    expect(provenanceNote('retailer_stated')).toBeNull()
    expect(provenanceNote('derived')).toContain('not stated by the retailer')
    expect(provenanceNote('user_confirmed')).toContain('You confirmed')
  })

  it('marks the derived rule in the fixture and leaves the stated ones clean', () => {
    const derived = FIXTURE_POLICY.rules.filter((rule) => rule.origin === 'derived')
    expect(derived).toHaveLength(1)
    expect(provenanceNote(derived[0]!.origin)).not.toBeNull()
  })

  /* §6.4: "`null` does not mean free". The fixture carries a null fee so the
     preview shows the case that is easiest to render wrongly. */
  it('keeps an unknown fee unknown', () => {
    expect(FIXTURE_POLICY.fee).toBeNull()
  })
})

describe('method labels', () => {
  /* The retailer chose these strings. Re-casing them to fit a sentence turned
     "QR code drop-off" into "qr code drop-off" — caught in a screenshot, not
     by a type. Nothing may transform a label on its way to the screen. */
  it('keeps acronym casing intact', () => {
    const qr = FIXTURE_METHODS.find((m) => m.methodId === 'qr_dropoff')!
    expect(qr.label).toBe('QR code drop-off')
    expect(`Use ${qr.label}`).toBe('Use QR code drop-off')
  })
})
