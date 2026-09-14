/**
 * The fields the manual fallback is allowed to put on screen.
 *
 * Frame I2's footnote promises that password, payment and file-upload fields
 * are excluded "manually or not". That promise has to be enforced somewhere
 * other than the copy, because the manual form is precisely the path where the
 * usual guard — the agent's closed action vocabulary — is not involved.
 *
 * The rule is an allowlist of kinds, not a denylist of names. A denylist has to
 * anticipate every spelling a retailer might use for a card field; an allowlist
 * only has to describe the three shapes we are willing to render.
 */
export const PERMITTED_KINDS = ['choice', 'short-text', 'long-text'] as const
export type FieldKind = (typeof PERMITTED_KINDS)[number]

export type ManualField = {
  name: string
  label: string
  kind: FieldKind
  /** For `choice`. The retailer's own option labels. */
  options?: string[]
  placeholder?: string
}

export function isPermittedKind(kind: string): kind is FieldKind {
  return (PERMITTED_KINDS as readonly string[]).includes(kind)
}

/**
 * Drops anything not on the allowlist rather than rendering it.
 *
 * Returns the survivors and the names of the casualties, because a field
 * silently vanishing from a form the user is trying to complete is its own
 * kind of bug — the screen should be able to say what it refused.
 */
export function permittedFields(fields: { name: string; kind: string }[]) {
  const allowed: string[] = []
  const refused: string[] = []
  for (const field of fields) {
    ;(isPermittedKind(field.kind) ? allowed : refused).push(field.name)
  }
  return { allowed, refused }
}

/* dev-note: the real list comes off the retailer's form via the extractor.
   These three are what frame I2 shows. */
export const FIXTURE_MANUAL_FIELDS: ManualField[] = [
  {
    name: 'return_method',
    label: 'Return method',
    kind: 'choice',
    options: ['QR code drop-off', 'Return in store', 'Prepaid label by mail'],
  },
  {
    name: 'reason',
    label: 'Reason',
    kind: 'choice',
    options: ['Too small', 'Changed my mind', 'Arrived damaged', 'Not as described'],
  },
  {
    name: 'note',
    label: 'Note to the retailer',
    kind: 'long-text',
    placeholder: 'Add anything they should know',
  },
]
