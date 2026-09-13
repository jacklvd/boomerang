import { FakeChromePermissions } from './chrome-permissions'
import { FakeChromeScripting } from './chrome-scripting'
import { FakeChromeStorage } from './chrome-storage'
import { FakeChromeTabs } from './chrome-tabs'
import { FakeClock } from './clock'
import { FakeWorkerLifecycle } from './worker-lifecycle'

export type FakeChrome = {
  storage: { local: FakeChromeStorage }
  tabs: FakeChromeTabs
  scripting: FakeChromeScripting
  permissions: FakeChromePermissions
  worker: FakeWorkerLifecycle
  clock: FakeClock
  /** Rebuilds every surface. Storage included — this is between tests, not a worker death. */
  reset: () => void
}

declare global {
  // eslint-disable-next-line no-var
  var chrome: FakeChrome | undefined
}

/**
 * Composes the fakes into one `globalThis.chrome` and returns it.
 *
 * dev-note: `reset()` clears storage too, because it stands for a fresh test,
 * not a terminated worker. Worker death is `worker.terminate()`, which drops
 * memory and deliberately leaves storage intact — conflating the two would make
 * the rehydration tests meaningless.
 */
export function installFakeChrome(): FakeChrome {
  const build = () => ({
    storage: { local: new FakeChromeStorage() },
    tabs: new FakeChromeTabs(),
    scripting: new FakeChromeScripting(),
    permissions: new FakeChromePermissions(),
    worker: new FakeWorkerLifecycle(),
    clock: new FakeClock(),
  })

  let surfaces = build()

  const fake: FakeChrome = {
    get storage() {
      return surfaces.storage
    },
    get tabs() {
      return surfaces.tabs
    },
    get scripting() {
      return surfaces.scripting
    },
    get permissions() {
      return surfaces.permissions
    },
    get worker() {
      return surfaces.worker
    },
    get clock() {
      return surfaces.clock
    },
    reset() {
      surfaces = build()
    },
  }

  globalThis.chrome = fake
  return fake
}

export function uninstallFakeChrome(): void {
  globalThis.chrome = undefined
}
