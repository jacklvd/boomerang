import { GlobeSimpleIcon, LockSimpleIcon } from '@phosphor-icons/react/dist/ssr'

import { Button } from './button'
import { PopupHeader } from './popup-header'

/**
 * Frame 01 of the designed popup flow — the scan gesture.
 *
 * It is the first screen for a reason that is architectural, not aesthetic: D7
 * gives the extension `activeTab`, which grants nothing on page load, so the
 * run cannot begin without the user acting. This screen is that act.
 *
 * dev-note: static. Nothing here reads a tab, a permission or a session yet —
 * the URL is a fixture. This exists to prove the scaffold renders the design,
 * and the next change replaces the fixture with the real active tab.
 */
export function App() {
  return (
    <div className="bg-bg">
      <PopupHeader status="Start" />

      <main className="flex flex-col gap-4 px-4 pt-[18px] pb-5">
        <span className="flex w-fit items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5">
          <GlobeSimpleIcon size={13} className="text-ink-faint" />
          <span className="text-[12.5px] text-ink-muted">nordstrom.com/orders</span>
        </span>

        <div className="flex flex-col gap-2">
          <h1 className="font-display text-[19px] leading-tight font-semibold text-ink">
            This looks like an order page.
          </h1>
          <p className="text-[13.5px] leading-[1.45] text-ink-muted">
            Boomerang can read the order list to find what is still returnable. It reads only when
            you ask it to.
          </p>
        </div>

        <div className="flex flex-col gap-2.5">
          <Button>Scan this page</Button>
          <Button variant="ghost">Not now</Button>
        </div>

        <p className="flex gap-2 text-[12px] leading-[1.45] text-ink-faint">
          <LockSimpleIcon size={13} className="mt-0.5 shrink-0 text-calm" />
          <span>
            We have no standing access to this site. Nothing was read before you tapped.
          </span>
        </p>
      </main>
    </div>
  )
}
