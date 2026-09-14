export class PermissionGestureError extends Error {
  constructor() {
    super('This function must be called during a user gesture')
    this.name = 'PermissionGestureError'
  }
}

/**
 * `contains`, `request` and `remove`, plus the gesture rule the real API
 * enforces: `request` outside a user gesture fails.
 *
 * dev-note: the gesture flag is the whole point. The two-tier permission design
 * depends on the first run being unable to acquire a standing host permission
 * without the user acting, and a double that granted silently would let that
 * requirement rot untested.
 */
export class FakeChromePermissions {
  #granted = new Set<string>()
  #inGesture = false
  #denyNext = false

  async contains({ origins }: { origins: string[] }): Promise<boolean> {
    return origins.every((origin) => this.#granted.has(origin))
  }

  async request({ origins }: { origins: string[] }): Promise<boolean> {
    if (!this.#inGesture) throw new PermissionGestureError()
    if (this.#denyNext) {
      this.#denyNext = false
      return false
    }
    for (const origin of origins) this.#granted.add(origin)
    return true
  }

  async remove({ origins }: { origins: string[] }): Promise<boolean> {
    for (const origin of origins) this.#granted.delete(origin)
    return true
  }

  /** Run `fn` as though the user had just clicked. */
  async duringGesture<T>(fn: () => Promise<T>): Promise<T> {
    this.#inGesture = true
    try {
      return await fn()
    } finally {
      this.#inGesture = false
    }
  }

  /** Make the next `request` come back denied. */
  denyNextRequest(): void {
    this.#denyNext = true
  }

  /** Test affordance: pre-grant without going through a gesture. */
  grant(...origins: string[]): void {
    for (const origin of origins) this.#granted.add(origin)
  }
}
