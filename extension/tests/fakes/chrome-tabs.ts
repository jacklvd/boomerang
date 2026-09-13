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

  async create({ url }: { url: string }): Promise<FakeTab> {
    const tab: FakeTab = { id: this.#nextId++, url, isLive: true }
    this.#tabs.set(tab.id, tab)
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
