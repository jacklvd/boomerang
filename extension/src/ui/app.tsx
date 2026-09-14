import { useEffect, useState } from 'react'
import { GlobeSimpleIcon, LockSimpleIcon, ProhibitIcon } from '@phosphor-icons/react/dist/ssr'

import {
  readActiveTab,
  scanActivePage,
  type ActiveTab,
  type PageProbe,
  type ScriptingArea,
  type TabsArea,
} from '@/src/tab/active-tab'
import { Button } from './button'
import { PopupHeader } from './popup-header'

type Scan =
  | { status: 'idle' }
  | { status: 'scanning' }
  | { status: 'scanned'; probe: PageProbe }
  | { status: 'failed'; message: string }

/**
 * Frame 01 of the designed popup flow — the scan gesture.
 *
 * It is the first screen for a reason that is architectural, not aesthetic. D7
 * gives the extension `activeTab`, which grants nothing on page load, so a run
 * cannot begin without the user acting. Opening this popup is that act: Chrome
 * hands over the current tab at that moment, which is why the URL below is
 * readable at all and why the footnote is literally true.
 *
 * Surfaces are props so the fakes can drive the same code the popup runs.
 */
export function App({ tabs, scripting }: { tabs: TabsArea; scripting: ScriptingArea }) {
  const [tab, setTab] = useState<ActiveTab | null>(null)
  const [scan, setScan] = useState<Scan>({ status: 'idle' })

  useEffect(() => {
    /* The rejection handler is not dead: `readActiveTab` resolves `unavailable`
       for every *expected* shape, but `tabs.query` itself can reject — chiefly
       "Extension context invalidated", when the extension reloads while the
       popup is open. Without this the promise rejects unhandled and `tab` stays
       null, so the popup sits on "Checking this tab…" forever. An honest
       "cannot see this tab" beats a spinner that never resolves. */
    readActiveTab(tabs).then(setTab, () => setTab({ kind: 'unavailable' }))
  }, [tabs])

  async function onScan(tabId: number) {
    setScan({ status: 'scanning' })
    try {
      setScan({ status: 'scanned', probe: await scanActivePage(scripting, tabId) })
    } catch (error) {
      setScan({ status: 'failed', message: messageFor(error) })
    }
  }

  return (
    <div className="bg-bg">
      <PopupHeader status="Start" onClose={() => window.close()} />
      <main className="flex flex-col gap-4 px-4 pt-[18px] pb-5">
        {tab === null ? <Waiting /> : <Screen tab={tab} scan={scan} onScan={onScan} />}
        <Footnote />
      </main>
    </div>
  )
}

function Screen({
  tab,
  scan,
  onScan,
}: {
  tab: ActiveTab
  scan: Scan
  onScan: (tabId: number) => void
}) {
  if (tab.kind === 'unavailable') {
    return (
      <Copy
        title="Boomerang cannot see this tab."
        body="Chrome has not handed this tab over. Open the popup from the page you want to read."
      />
    )
  }

  if (tab.kind === 'blocked') {
    return (
      <>
        <Chip label={tab.label} blocked />
        <Copy
          title="Chrome keeps this page to itself."
          body="No extension can read a browser page, the Web Store, or a local file. That is the browser's rule, not ours."
        />
      </>
    )
  }

  return (
    <>
      <Chip label={tab.label} />
      {scan.status === 'scanned' ? (
        <Copy
          title="Read it."
          body={`Found ${plural(scan.probe.rowCount, 'candidate row')} on the page. Nothing has left your browser.`}
        />
      ) : (
        <Copy
          title={tab.looksLikeOrders ? 'This looks like an order page.' : 'Scan this one anyway?'}
          body={
            tab.looksLikeOrders
              ? 'Boomerang can read the order list to find what is still returnable. It reads only when you ask it to.'
              : 'This does not look like an order list, but the guess is made from the address alone. Scan it and find out.'
          }
        />
      )}

      {scan.status === 'failed' && (
        <p className="rounded-[10px] bg-urgent-soft px-3 py-2.5 text-[12.5px] text-urgent">
          {scan.message}
        </p>
      )}

      <div className="flex flex-col gap-2.5">
        <Button onClick={() => onScan(tab.tabId)} disabled={scan.status === 'scanning'}>
          {scan.status === 'scanning'
            ? 'Reading…'
            : scan.status === 'idle'
              ? 'Scan this page'
              : 'Scan again'}
        </Button>
        <Button variant="ghost" onClick={() => window.close()}>
          Not now
        </Button>
      </div>
    </>
  )
}

/* dev-note: the designed flow answers a finished scan with frame 02 and then
   frame 03, which show progress and the normalised order. Neither exists yet
   and neither can until the extractor does, so a scan reports a count and
   stops. Replace this branch, not the wiring above it. */
function plural(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}

function messageFor(error: unknown) {
  return error instanceof Error ? error.message : 'the scan did not finish'
}

function Waiting() {
  return <p className="py-6 text-[13.5px] text-ink-faint">Checking this tab…</p>
}

function Copy({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="font-display text-[19px] leading-tight font-semibold text-ink">{title}</h1>
      <p className="text-[13.5px] leading-[1.45] text-ink-muted">{body}</p>
    </div>
  )
}

function Chip({ label, blocked = false }: { label: string; blocked?: boolean }) {
  const Icon = blocked ? ProhibitIcon : GlobeSimpleIcon
  return (
    <span className="flex w-fit items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5">
      <Icon size={13} className={blocked ? 'text-urgent' : 'text-ink-faint'} />
      <span className="text-[12.5px] text-ink-muted">{label}</span>
    </span>
  )
}

function Footnote() {
  return (
    <p className="flex gap-2 text-[12px] leading-[1.45] text-ink-faint">
      <LockSimpleIcon size={13} className="mt-0.5 shrink-0 text-calm" />
      <span>We have no standing access to this site. Nothing was read before you tapped.</span>
    </p>
  )
}
