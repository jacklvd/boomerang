/**
 * Durable storage for `WorkflowSession`, the extension-local workflow record.
 *
 * This is the seam between the two halves of the MV3 storage model: memory is
 * disposable and dies with the worker, `chrome.storage.local` is what survives.
 * Everything a revived worker knows about a run in progress it learns from
 * here, which is why every read goes through `parseWorkflowSession` and every
 * write goes through it first.
 */
import {
  parseWorkflowSession,
  type WorkflowSession,
} from '../model/workflow'

/**
 * The slice of `chrome.storage.StorageArea` this store uses.
 *
 * Injected rather than reached for, so the store can run against the real area
 * and the test double without `src/` importing anything from `tests/`. Both
 * satisfy this structurally; neither had to be written to fit it.
 */
export type StorageArea = {
  get(keys?: string | string[] | null): Promise<Record<string, unknown>>
  set(items: Record<string, unknown>): Promise<void>
  remove(keys: string | string[]): Promise<void>
}

const KEY_PREFIX = 'workflow_session:'

/**
 * §9: an item has at most one active session, so the item identifier is the
 * key. Identifiers are opaque (§3.1) and may contain anything, which is why
 * membership is a prefix test and never a split on the separator.
 */
export function sessionKey(itemId: string): string {
  return `${KEY_PREFIX}${itemId}`
}

export class WorkflowSessionStore {
  #area: StorageArea

  constructor(area: StorageArea) {
    this.#area = area
  }

  /**
   * Reads one session, or `null` when there isn't a usable one.
   *
   * An unparseable record is deleted rather than returned or left in place. It
   * cannot be acted on, and leaving it means every subsequent worker wake-up
   * re-reads and re-rejects the same garbage — a permanent failure the user has
   * no way to clear. Dropping it costs one interrupted run and restores a
   * working extension.
   */
  async read(itemId: string): Promise<WorkflowSession | null> {
    const key = sessionKey(itemId)
    const stored = await this.#area.get(key)
    if (!(key in stored)) return null

    const parsed = parseWorkflowSession(stored[key])
    if (parsed.ok) return parsed.value

    await this.#discard(key, parsed.reason)
    return null
  }

  /**
   * Validates before writing. The type checker already guarantees the shape;
   * what it cannot check is the content — a timestamp with an offset, a
   * `javascript:` URL, a lowercase currency code. Those are exactly the records
   * that later fail to read back, so the write is the cheapest place to stop
   * them. An invalid write is a bug in the caller, not an expected outcome, so
   * this throws where `read` returns null.
   *
   * A quota rejection propagates untouched. Swallowing it would report a stored
   * run that is not stored.
   */
  async write(session: WorkflowSession): Promise<void> {
    const parsed = parseWorkflowSession(session)
    if (!parsed.ok) throw new Error(`refusing to store an invalid session: ${parsed.reason}`)
    await this.#area.set({ [sessionKey(session.item_id)]: parsed.value })
  }

  async clear(itemId: string): Promise<void> {
    await this.#area.remove(sessionKey(itemId))
  }

  /**
   * Every usable session. Unparseable records are dropped as in `read`.
   *
   * dev-note: scans the whole area, since there is no index and a user has a
   * handful of concurrent returns rather than thousands. Add a key index if
   * that stops being true.
   */
  async list(): Promise<WorkflowSession[]> {
    const stored = await this.#area.get(null)
    const sessions: WorkflowSession[] = []

    for (const [key, value] of Object.entries(stored)) {
      if (!key.startsWith(KEY_PREFIX)) continue
      const parsed = parseWorkflowSession(value)
      if (parsed.ok) sessions.push(parsed.value)
      else await this.#discard(key, parsed.reason)
    }
    return sessions
  }

  /* dev-note: the service worker's console is the only place a discarded run
     surfaces. Losing state silently is what makes this class of bug take a
     week to find. */
  async #discard(key: string, reason: string): Promise<void> {
    console.warn(`[boomerang] discarding unreadable ${key}: ${reason}`)
    await this.#area.remove(key)
  }
}
