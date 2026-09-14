/**
 * A service worker that can actually die.
 *
 * MV3 terminates the worker whenever it feels like it, and the design's answer
 * is that durable state lives in `chrome.storage.local` while in-memory state
 * is disposable. `terminate()` therefore has to genuinely drop memory: a double
 * that kept it would let every worker-death test pass without proving anything,
 * which is worse than having no test.
 */
export class FakeWorkerLifecycle {
  #memory = new Map<string, unknown>()
  #generation = 0
  #rehydrations = 0

  /** Increments on every termination, so a test can prove memory was rebuilt. */
  get generation(): number {
    return this.#generation
  }

  get rehydrations(): number {
    return this.#rehydrations
  }

  remember(key: string, value: unknown): void {
    this.#memory.set(key, value)
  }

  recall(key: string): unknown {
    return this.#memory.get(key)
  }

  /** Drops all in-memory state. Storage is a separate fake and survives. */
  terminate(): void {
    this.#memory.clear()
    this.#generation += 1
  }

  /**
   * Runs `rehydrate` only when memory is cold, the way a revived worker has to
   * read its state back before it can do anything.
   */
  async withRehydration<T>(key: string, rehydrate: () => Promise<T>): Promise<T> {
    if (this.#memory.has(key)) return this.#memory.get(key) as T
    this.#rehydrations += 1
    const value = await rehydrate()
    this.#memory.set(key, value)
    return value
  }
}
