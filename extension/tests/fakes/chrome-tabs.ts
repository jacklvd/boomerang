export type FakeTab = {
  id: number
  url: string
  /** False once the tab is closed. A driver holding a handle must notice. */
  isLive: boolean
}

type RemovedListener = (tabId: number) => void

export class FakeChromeTabs {
  #tabs = new Map<number, FakeTab>()
  #nextId = 1
  #onRemoved: RemovedListener[] = []
  #activeId: number | null = null

  async create({ url }: { url: string }): Promise<FakeTab> {
    const tab: FakeTab = { id: this.#nextId++, url, isLive: true }
    this.#tabs.set(tab.id, tab)
    this.#activeId ??= tab.id
    return { ...tab }
  }

  async get(tabId: number): Promise<FakeTab> {
    const tab = this.#tabs.get(tabId)
    if (!tab) throw new Error(`No tab with id ${tabId}`)
    return { ...tab }
  }

  async update(tabId: number, { url }: { url: string }): Promise<FakeTab> {
    const tab = this.#requireLive(tabId)
    tab.url = url
    return { ...tab }
  }

  async remove(tabId: number): Promise<void> {
    const tab = this.#tabs.get(tabId)
    if (!tab) return
    tab.isLive = false
    for (const listener of this.#onRemoved) listener(tabId)
  }

  onRemoved = {
    addListener: (listener: RemovedListener) => {
      this.#onRemoved.push(listener)
    },
  }

  /**
   * Matches `chrome.tabs.query` closely enough for the one query the popup
   * makes. It answers with an empty array when nothing is active, because that
   * is what the real API does on a devtools window or an empty new-tab state —
   * a popup that assumed a tab was always there would crash exactly there.
   */
  async query(_query: { active?: boolean; currentWindow?: boolean }): Promise<FakeTab[]> {
    if (this.#activeId === null) return []
    const tab = this.#tabs.get(this.#activeId)
    return tab && tab.isLive ? [{ ...tab }] : []
  }

  /** Test affordance: which tab the user is looking at. */
  activate(tabId: number): void {
    this.#activeId = tabId
  }

  /** Test affordance: no tab is active at all. */
  deactivate(): void {
    this.#activeId = null
  }

  /** Test affordance: the page navigated under the driver's feet. */
  setUrl(tabId: number, url: string): void {
    this.#requireLive(tabId).url = url
  }

  isLive(tabId: number): boolean {
    return this.#tabs.get(tabId)?.isLive ?? false
  }

  #requireLive(tabId: number): FakeTab {
    const tab = this.#tabs.get(tabId)
    if (!tab) throw new Error(`No tab with id ${tabId}`)
    if (!tab.isLive) throw new Error(`Tab ${tabId} is closed`)
    return tab
  }
}
