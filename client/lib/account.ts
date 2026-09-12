/**
 * Stands in for the session the server will own once Google sign-in exists.
 *
 * D10: Google is the v1 account provider and the backend keys the user by the
 * OIDC `sub`. Nothing here is durable — there is no auth endpoint yet, so these
 * flip by hand to walk each state.
 */

export type Account = {
  /** The OIDC `sub`. Stable across email changes, which is why it is the key. */
  sub: string
  name: string
  email: string
  /** Google's avatar URL. Null until a real grant supplies one. */
  avatarUrl: string | null
}

/* dev-note: flip to null to see the signed-out dashboard. */
export const CURRENT_ACCOUNT: Account | null = {
  sub: '117482910384756201938',
  name: 'Jackie Vo',
  email: 'jackie@example.com',
  avatarUrl: null,
}

export const initialsOf = (name: string) =>
  name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
