import { describe, expect, it } from 'vitest'

import { sanitize, redactionTotal } from '../src/extract/sanitize'
import type { Capture, CapturedNode } from '../src/extract/capture'

const node = (partial: Partial<CapturedNode> & { tag: string }): CapturedNode => ({
  attrs: {},
  ...partial,
})

const capture = (root: CapturedNode | null): Capture => ({
  root,
  nodeCount: 1,
  truncated: false,
})

const textOf = (root: CapturedNode | null): string[] => {
  const out: string[] = []
  const walk = (n: CapturedNode) => {
    if (n.text !== undefined) out.push(n.text)
    n.children?.forEach(walk)
  }
  if (root) walk(root)
  return out
}

describe('card numbers', () => {
  it('redacts a number that passes Luhn, in any of its written forms', () => {
    for (const written of ['4111111111111111', '4111 1111 1111 1111', '4111-1111-1111-1111']) {
      const { root, report } = sanitize(capture(node({ tag: 'p', text: `Paid with ${written}` })))
      expect(textOf(root)[0], written).toBe('Paid with [redacted:card]')
      expect(report.redactions['card-number']).toBe(1)
    }
  })

  /* The check exists so a 16-digit order reference is not reported as a card.
     It still disappears — as a long digit run, which is redacted anyway — so
     Luhn buys accuracy in the report, not a different outcome on the wire.
     Note 1234567812345670 *is* Luhn-valid: a reference can be, by chance, and
     this guard errs towards redacting when it is. */
  it('does not call a non-Luhn reference a card number', () => {
    const { report } = sanitize(capture(node({ tag: 'p', text: 'Order 1234567812345678' })))
    expect(report.redactions['card-number']).toBe(0)
    expect(report.redactions['long-digit-run']).toBe(1)
  })

  it('leaves an ordinary price alone', () => {
    const { root, report } = sanitize(capture(node({ tag: 'p', text: '$180.00 · Qty 1' })))
    expect(textOf(root)[0]).toBe('$180.00 · Qty 1')
    expect(redactionTotal(report)).toBe(0)
  })
})

describe('emails and long digit runs', () => {
  it('redacts an email address', () => {
    const { root } = sanitize(capture(node({ tag: 'p', text: 'Sent to jack@example.com today' })))
    expect(textOf(root)[0]).toBe('Sent to [redacted:email] today')
  })

  /* A tracking number, a barcode, and the digits printed under a QR code are
     all the same shape, and all three are on the never-leaves list. */
  it('redacts a run long enough to be a barcode or tracking number', () => {
    const { root, report } = sanitize(
      capture(node({ tag: 'p', text: 'Tracking 9400111899223197428490' })),
    )
    expect(textOf(root)[0]).toBe('Tracking [redacted:digits]')
    expect(report.redactions['long-digit-run']).toBe(1)
  })

  it('leaves a short reference readable', () => {
    const { root } = sanitize(capture(node({ tag: 'p', text: 'Order #114-2280' })))
    expect(textOf(root)[0]).toBe('Order #114-2280')
  })
})

describe('address containers', () => {
  const shipping = (attrs: Record<string, string>) =>
    node({
      tag: 'div',
      attrs,
      children: [node({ tag: 'span', text: '1412 Alder St, Portland OR 97209' })],
    })

  it('redacts everything under a container that names itself', () => {
    const cases: Record<string, string>[] = [
      { class: 'shipping-address' },
      { id: 'billingAddress' },
      { 'data-testid': 'deliver-to' },
      { itemprop: 'address' },
    ]
    for (const attrs of cases) {
      const { root, report } = sanitize(capture(shipping(attrs)))
      expect(textOf(root), JSON.stringify(attrs)).toEqual(['[redacted:address]'])
      expect(report.redactions['address-container']).toBe(1)
    }
  })

  it('redacts the whole subtree, not just the labelled node', () => {
    const { root } = sanitize(
      capture(
        node({
          tag: 'section',
          attrs: { class: 'shipping' },
          children: [
            node({ tag: 'h2', text: 'Delivered to' }),
            node({ tag: 'p', text: '1412 Alder St' }),
            node({ tag: 'p', text: 'Portland OR 97209' }),
          ],
        }),
      ),
    )
    expect(textOf(root).every((t) => t === '[redacted:address]')).toBe(true)
  })

  it('redacts an <address> element without needing a class', () => {
    const { root } = sanitize(
      capture(node({ tag: 'address', children: [node({ tag: 'span', text: '1412 Alder St' })] })),
    )
    expect(textOf(root)).toEqual(['[redacted:address]'])
  })

  /* The word has to be a token, or every "Order addressed to you" heading and
     every class containing "readdress" would vanish. */
  it('does not fire on a word that merely contains the token', () => {
    const { report } = sanitize(
      capture(node({ tag: 'div', attrs: { class: 'readdressed' }, children: [] })),
    )
    expect(report.redactions['address-container']).toBe(0)
  })
})

describe('declared sensitive fields', () => {
  it('reports a field the page itself declares sensitive', () => {
    for (const autocomplete of [
      'cc-number',
      'cc-csc',
      'street-address',
      'address-line1',
      'postal-code',
      'current-password',
      'one-time-code',
    ]) {
      const { report } = sanitize(
        capture(node({ tag: 'input', attrs: { type: 'text', autocomplete } })),
      )
      expect(report.redactions['declared-sensitive-field'], autocomplete).toBe(1)
    }
  })

  it('leaves an ordinary field unreported', () => {
    const { report } = sanitize(
      capture(node({ tag: 'input', attrs: { type: 'search', autocomplete: 'off' } })),
    )
    expect(redactionTotal(report)).toBe(0)
  })
})

describe('the report', () => {
  it('carries truncation through, so the server knows the tree is partial', () => {
    const { report } = sanitize({ root: null, nodeCount: 1500, truncated: true })
    expect(report).toMatchObject({ truncated: true, nodeCount: 1500 })
  })

  it('counts every redaction it made', () => {
    const { report } = sanitize(
      capture(
        node({
          tag: 'div',
          children: [
            node({ tag: 'p', text: 'jack@example.com' }),
            node({ tag: 'p', text: '4111 1111 1111 1111' }),
            node({ tag: 'address', children: [node({ tag: 'p', text: '1412 Alder St' })] }),
          ],
        }),
      ),
    )
    expect(redactionTotal(report)).toBe(3)
  })

  it('survives an empty capture', () => {
    expect(sanitize(capture(null)).root).toBeNull()
  })
})

describe('what it does not touch', () => {
  /* The capture never picks up a form value, so the guard never has to remove
     one. This pins that the pass does not accidentally invent an attribute. */
  it('adds no attribute the capture did not carry', () => {
    const input = node({ tag: 'input', attrs: { type: 'password' } })
    const { root } = sanitize(capture(input))
    expect(root?.attrs).toEqual({ type: 'password' })
  })
})
