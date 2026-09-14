/**
 * The egress guard: the last thing that runs before a capture may leave the
 * browser.
 *
 * The retention baseline gives raw and sanitized DOM zero durable retention,
 * and names what must never leave at all — labels, QR contents, addresses,
 * barcodes, protected URLs, cookies, auth headers, passwords, payment fields,
 * file inputs. `captureOrderSubtree` already refuses to pick most of those up.
 * This pass exists for what survives being picked up anyway: content that is
 * sensitive because of what it *says*, not where it sits.
 *
 * Pure, and deliberately separate from the capture. The capture runs in the
 * page and cannot be imported by tests without a DOM; this runs in the
 * extension over a plain tree, so every rule below is directly testable.
 *
 * ## What it does not solve
 *
 * A street address written as ordinary prose, in a container that does not
 * declare itself, is not detected. Detecting one by pattern would be guesswork
 * with a false-negative rate nobody can state, so this guard does not claim to.
 * The structural rules below catch the case that actually occurs on an order
 * page — the address sits in something labelled "shipping-address" — and the
 * residual gap is a real open risk for the terminal-page sanitizer, which is
 * where addresses are most likely to appear free-form. Tracked as issue #34,
 * which should be settled before `report_outcome` is built: do not reach for
 * this guard to sanitize a terminal page without reading it first.
 */
import type { Capture, CapturedNode } from './capture'

export type RedactionKind =
  | 'card-number'
  | 'email'
  | 'long-digit-run'
  | 'declared-sensitive-field'
  | 'address-container'

export type SanitizeReport = {
  redactions: Record<RedactionKind, number>
  /** True when the capture was already partial, carried through for the server. */
  truncated: boolean
  nodeCount: number
}

export type Sanitized = {
  root: CapturedNode | null
  report: SanitizeReport
}

/**
 * `autocomplete` tokens that declare a field holds something we must not carry.
 * A standards-defined declaration beats a heuristic: the page is telling us.
 */
const SENSITIVE_AUTOCOMPLETE =
  /^(cc-|street-address|address-line|address-level|postal-code|country|tel|email|new-password|current-password|one-time-code)/i

/** Containers that name themselves as holding an address or a recipient. */
const ADDRESS_CONTAINER = /(^|[-_\s])(address|shipping|billing|recipient|deliver[-_]?to)/i

const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/g
/** 12+ digits: tracking numbers, barcodes, and the digits under a QR code. */
const LONG_DIGITS = /\d[\d\s-]{10,}\d/g
const CARD_CANDIDATE = /\b(?:\d[ -]?){12,18}\d\b/g

const PLACEHOLDER: Record<RedactionKind, string> = {
  'card-number': '[redacted:card]',
  email: '[redacted:email]',
  'long-digit-run': '[redacted:digits]',
  'declared-sensitive-field': '[redacted:field]',
  'address-container': '[redacted:address]',
}

/**
 * Luhn, so a 16-digit order reference is not mistaken for a card number.
 *
 * The check runs in the direction that matters: it decides whether to redact
 * *more*, and a false positive costs one unreadable order number while a false
 * negative puts a card number on the wire.
 */
function looksLikeCard(digits: string): boolean {
  if (digits.length < 13 || digits.length > 19) return false
  let sum = 0
  let double = false
  for (let i = digits.length - 1; i >= 0; i -= 1) {
    let value = digits.charCodeAt(i) - 48
    if (double) {
      value *= 2
      if (value > 9) value -= 9
    }
    sum += value
    double = !double
  }
  return sum % 10 === 0
}

function selfDescribes(node: CapturedNode, pattern: RegExp): boolean {
  for (const key of ['class', 'id', 'data-testid', 'itemprop'] as const) {
    const value = node.attrs[key]
    if (value && pattern.test(value)) return true
  }
  return false
}

export function sanitize(capture: Capture): Sanitized {
  const redactions: Record<RedactionKind, number> = {
    'card-number': 0,
    email: 0,
    'long-digit-run': 0,
    'declared-sensitive-field': 0,
    'address-container': 0,
  }

  const count = (kind: RedactionKind) => {
    redactions[kind] += 1
    return PLACEHOLDER[kind]
  }

  const scrubText = (text: string): string =>
    text
      .replace(CARD_CANDIDATE, (match) =>
        looksLikeCard(match.replace(/\D/g, '')) ? count('card-number') : match,
      )
      .replace(EMAIL, () => count('email'))
      .replace(LONG_DIGITS, () => count('long-digit-run'))

  const visit = (node: CapturedNode, inAddress: boolean): CapturedNode => {
    const out: CapturedNode = { tag: node.tag, attrs: { ...node.attrs } }

    const declared = out.attrs.autocomplete
    if (declared && SENSITIVE_AUTOCOMPLETE.test(declared)) {
      /* The control carries no value already — the capture never reads one.
         Recording it keeps the guard's report honest about what it saw. */
      count('declared-sensitive-field')
    }

    const address = inAddress || node.tag === 'address' || selfDescribes(node, ADDRESS_CONTAINER)

    if (node.text !== undefined) {
      if (address) {
        out.text = count('address-container')
      } else {
        const scrubbed = scrubText(node.text)
        if (scrubbed) out.text = scrubbed
      }
    }

    if (node.children?.length) {
      out.children = node.children.map((child) => visit(child, address))
    }
    return out
  }

  return {
    root: capture.root ? visit(capture.root, false) : null,
    report: { redactions, truncated: capture.truncated, nodeCount: capture.nodeCount },
  }
}

/** Whether the guard removed anything. Drives what the popup can honestly say. */
export function redactionTotal(report: SanitizeReport): number {
  return Object.values(report.redactions).reduce((sum, n) => sum + n, 0)
}
