/**
 * `executeScript` returns whatever the test staged for that tab — a DOM string,
 * or the structured value an injected function would return. Staging is a
 * queue, so a test can walk a tab through several steps and assert that the
 * driver read each one — the point of the double is that the page changes
 * between observations.
 */
export class FakeChromeScripting {
  #staged = new Map<number, unknown[]>()

  /** Stage one or more successive results for a tab. */
  stage(tabId: number, ...results: unknown[]): void {
    const queue = this.#staged.get(tabId) ?? []
    queue.push(...results)
    this.#staged.set(tabId, queue)
  }

  async executeScript<T = unknown>({
    target,
  }: {
    target: { tabId: number }
  }): Promise<{ result: T }[]> {
    const queue = this.#staged.get(target.tabId)
    if (!queue || queue.length === 0) {
      throw new Error(
        `No DOM staged for tab ${target.tabId}. Call stage() — a silent empty read would look ` +
          `like an empty page rather than a missing fixture.`,
      )
    }
    // The last staged result repeats, so a test that reads twice without
    // staging twice gets a stable page rather than an error.
    const result = queue.length > 1 ? queue.shift() : queue[0]
    return [{ result: result as T }]
  }
}
