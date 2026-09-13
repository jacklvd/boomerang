/**
 * A `chrome.storage.local` double that reproduces the three properties the real
 * API has and the design depends on: per-`set` atomicity, a hard quota, and a
 * `getBytesInUse` consistent with what was actually written.
 *
 * dev-note: the point is to be *unhelpful* in the same places the real API is.
 * A forgiving double hides the bugs worth catching — most of all that
 * `chrome.storage.local` offers no multi-key transaction across separate `set`
 * calls, which is the reason the workflow state needs a safe checkpoint at all.
 */

export type StorageRecord = Record<string, unknown>

/** Chrome's documented `local` quota. */
export const DEFAULT_QUOTA_BYTES = 10 * 1024 * 1024

export class QuotaExceededError extends Error {
  constructor(bytes: number, quota: number) {
    super(`Resource::kQuotaBytes quota exceeded: ${bytes} > ${quota}`)
    this.name = 'QuotaExceededError'
  }
}

/**
 * Measures the way Chrome documents it: the JSON serialization of each value
 * plus its key. Computed, never stubbed — eviction logic measures with this,
 * and would pass against a double that lied about sizes.
 */
export function measure(key: string, value: unknown): number {
  return key.length + JSON.stringify(value ?? null).length
}

export class FakeChromeStorage {
  #data = new Map<string, unknown>()
  #quotaBytes: number
  #armedRejection = false

  constructor(quotaBytes = DEFAULT_QUOTA_BYTES) {
    this.#quotaBytes = quotaBytes
  }

  /** Make the next `set` fail the way the real API does under quota pressure. */
  armQuotaRejection(): void {
    this.#armedRejection = true
  }

  async get(keys?: string | string[] | null): Promise<StorageRecord> {
    const wanted =
      keys == null ? [...this.#data.keys()] : Array.isArray(keys) ? keys : [keys]

    const out: StorageRecord = {}
    for (const key of wanted) {
      if (this.#data.has(key)) out[key] = structuredClone(this.#data.get(key))
    }
    return out
  }

  /**
   * Applies wholly or not at all. The real API commits one `set` atomically;
   * what it does *not* give you is atomicity across two of them.
   */
  async set(items: StorageRecord): Promise<void> {
    const staged = new Map(this.#data)
    for (const [key, value] of Object.entries(items)) {
      staged.set(key, structuredClone(value))
    }

    const projected = FakeChromeStorage.#bytesOf(staged)

    if (this.#armedRejection) {
      this.#armedRejection = false
      throw new QuotaExceededError(projected, this.#quotaBytes)
    }
    if (projected > this.#quotaBytes) {
      throw new QuotaExceededError(projected, this.#quotaBytes)
    }

    this.#data = staged
  }

  async remove(keys: string | string[]): Promise<void> {
    for (const key of Array.isArray(keys) ? keys : [keys]) this.#data.delete(key)
  }

  async clear(): Promise<void> {
    this.#data.clear()
  }

  async getBytesInUse(keys?: string | string[] | null): Promise<number> {
    if (keys == null) return FakeChromeStorage.#bytesOf(this.#data)

    let total = 0
    for (const key of Array.isArray(keys) ? keys : [keys]) {
      if (this.#data.has(key)) total += measure(key, this.#data.get(key))
    }
    return total
  }

  static #bytesOf(data: Map<string, unknown>): number {
    let total = 0
    for (const [key, value] of data) total += measure(key, value)
    return total
  }
}
