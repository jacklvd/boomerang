import { useEffect, useState } from 'react'
import { GlobeSimpleIcon, LockSimpleIcon, ProhibitIcon } from '@phosphor-icons/react/dist/ssr'

import {
  readActiveTab,
  scanActivePage,
  type ActiveTab,
  type ScanResult,
  type ScriptingArea,
  type TabsArea,
} from '@/src/tab/active-tab'
import { FIXTURE_ORDER, toggleSelection } from '@/src/model/read-order'
import { Button } from './button'
import { OrderReview } from './order-review'
import { PopupHeader } from './popup-header'
import { PREVIEW, type PreviewScreen } from './preview'
import { FIXTURE_POLICY } from '@/src/model/policy'
import { initialSelection, FIXTURE_METHODS, FIXTURE_REASONS } from '@/src/model/return-flow'
import { MethodPicker } from './method-picker'
import { PolicySummary } from './policy-summary'
import { ReasonPicker } from './reason-picker'
import { ReviewSubmit } from './review-submit'
import { FIXTURE_MANUAL_FIELDS } from '@/src/model/manual-entry'
import { formatSavedAt, resumeView } from '@/src/model/resume'
import { WORKFLOW_SCHEMA_VERSION } from '@/src/model/workflow'
import { FIXTURE_RUNNING, FIXTURE_STUCK } from '@/src/model/agent-log'
import { FIXTURE_EPHEMERAL } from '@/src/model/outcome'
import { CalendarOffer } from './calendar-offer'
import { DriverLog } from './driver-log'
import { Finished } from './finished'
import { ManualForm } from './manual-form'
import { OutcomeReady } from './outcome-ready'
import { ResumeRun } from './resume-run'
import { ScanProgress } from './scan-progress'
import { StandingAccess } from './standing-access'

type Scan =
  | { status: 'idle' }
  | { status: 'scanning' }
  | { status: 'scanned'; result: ScanResult }
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
      setScan({ status: 'scanned', result: await scanActivePage(scripting, tabId) })
    } catch (error) {
      setScan({ status: 'failed', message: messageFor(error) })
    }
  }

  if (PREVIEW) return <Preview screen={PREVIEW} />

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

const PREVIEW_SESSION = {
  schema_version: WORKFLOW_SCHEMA_VERSION,
  id: 'wfs_preview',
  account_id: 'acct_1',
  order_id: 'order_1',
  item_id: 'read_1',
  run_status: 'awaiting_user',
  retailer_step: 'select_method',
  tab_id: 42,
  last_validated_url: 'https://retailer.example/returns',
  safe_checkpoint: null,
  fields_filled: [],
  suggested_reason: 'too_small',
  user_confirmed_reason: 'Too small',
  selected_return_method: null,
  attempt_count: 1,
  started_at: '2026-09-03T21:14:00Z',
  updated_at: '2026-09-03T21:14:00Z',
} as const

const STATUS: Record<PreviewScreen, string> = {
  reading: 'Step 1 of 6',
  order: 'Step 2 of 6',
  reason: 'Step 3 of 6',
  'change-method': 'Step 5 of 6 · Editing',
  manual: 'Step 5 of 6 · Manual',
  resume: 'Resumed',
  driving: 'Working',
  stuck: 'Stopped',
  outcome: 'Done',
  calendar: 'Optional',
  finished: 'Complete',
  policy: 'Step 4 of 6',
  method: 'Step 5 of 6',
  review: 'Step 6 of 6',
  'standing-access': 'Optional',
}

/* dev-note: reachable only by editing PREVIEW. See the note on that constant. */
function Preview({ screen }: { screen: PreviewScreen }) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(
    () => new Set(FIXTURE_ORDER.items.map((item) => item.localId)),
  )
  const [reasonId, setReasonId] = useState<string | null>(FIXTURE_REASONS[0]?.id ?? null)
  const [methodId, setMethodId] = useState<string | null>(() => initialSelection(FIXTURE_METHODS))

  return (
    <div className="bg-bg">
      <PopupHeader status={STATUS[screen]} onClose={() => window.close()} />
      <main className="flex flex-col gap-4 px-4 pt-[18px] pb-5">
        {screen === 'driving' ? (
          <DriverLog entries={FIXTURE_RUNNING} onTakeOver={() => {}} />
        ) : screen === 'stuck' ? (
          <DriverLog
            entries={FIXTURE_STUCK}
            deadlineNote="The window still closes on 17 September. The tab is open on the right page — finish it by hand and we will pick the record back up."
            onTakeOver={() => {}}
            onReport={() => {}}
          />
        ) : screen === 'outcome' ? (
          <OutcomeReady
            outcome="qr_ready"
            details={FIXTURE_EPHEMERAL}
            onAddReminder={() => {}}
            onSaveCode={() => {}}
          />
        ) : screen === 'calendar' ? (
          <CalendarOffer
            retailerName="Nordstrom"
            returnBy="2026-09-17"
            onOpenCalendar={() => {}}
            onDecline={() => {}}
          />
        ) : screen === 'finished' ? (
          <Finished
            summary={{
              item: 'Wool Overcoat, Charcoal',
              method: 'QR code drop-off · Free',
              reference: 'RMA 8842-QK21',
              refund: '$180.00 to original card',
              dropOffBy: '2026-09-17',
            }}
            onSeeReturns={() => {}}
          />
        ) : screen === 'change-method' ? (
          /* The user arrived here by rejecting the pre-filled method, so the
             previously chosen one is marked and something else is selected. */
          <MethodPicker
            options={FIXTURE_METHODS}
            selectedId={methodId === 'qr_dropoff' ? 'in_store' : methodId}
            onSelect={setMethodId}
            onContinue={() => {}}
            title="Pick a different method"
            body="Your item and reason are kept. Only this choice changes."
            previouslyChosenId="qr_dropoff"
          />
        ) : screen === 'manual' ? (
          <ManualForm
            fields={FIXTURE_MANUAL_FIELDS}
            values={{ return_method: 'QR code drop-off', reason: 'Too small' }}
            onChange={() => {}}
            onSubmit={() => {}}
            onBack={() => {}}
          />
        ) : screen === 'resume' ? (
          <ResumeRun
            view={resumeView(PREVIEW_SESSION, { returnBy: '2026-09-16', tabIsLive: true })}
            itemDescription="Wool Overcoat, Charcoal"
            retailerName="Nordstrom"
            savedAt={formatSavedAt(PREVIEW_SESSION.updated_at)}
            onContinue={() => {}}
            onStartOver={() => {}}
          />
        ) : screen === 'reason' ? (
          <ReasonPicker
            reasons={FIXTURE_REASONS}
            selectedId={reasonId}
            onSelect={setReasonId}
            onContinue={() => {}}
            onSkip={() => {}}
          />
        ) : screen === 'policy' ? (
          <PolicySummary
            retailerName="Nordstrom"
            policy={FIXTURE_POLICY}
            onContinue={() => {}}
            onOpenDashboard={() => {}}
          />
        ) : screen === 'method' ? (
          <MethodPicker
            options={FIXTURE_METHODS}
            selectedId={methodId}
            onSelect={setMethodId}
            onContinue={() => {}}
          />
        ) : screen === 'review' ? (
          <ReviewSubmit
            summary={{
              items: 'Wool Overcoat, Charcoal · $180.00',
              reason: FIXTURE_REASONS.find((r) => r.id === reasonId)?.label ?? null,
              method: FIXTURE_METHODS.find((m) => m.methodId === methodId)?.label ?? null,
              refundTo: 'Original payment method',
            }}
            onEdit={() => {}}
            onSubmit={() => {}}
            onChangeMethod={() => {}}
          />
        ) : screen === 'standing-access' ? (
          <StandingAccess
            hostname="nordstrom.com"
            onAllow={() => {}}
            onDecline={() => {}}
          />
        ) : screen === 'reading' ? (
          <ScanProgress
            stages={[
              { label: 'Found the order list', state: 'done' },
              { label: 'Normalising items and prices', state: 'done' },
              { label: 'Reading delivery dates', state: 'running' },
              { label: 'Checking return windows', state: 'pending' },
            ]}
          />
        ) : (
          <OrderReview
            order={FIXTURE_ORDER}
            selected={selected}
            onToggle={(id) => setSelected((prev) => toggleSelection(prev, id))}
            onConfirm={() => {}}
            onReject={() => {}}
          />
        )}
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
        <Copy title="Read it." body={scanSummary(scan.result)} />
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

/**
 * dev-note: the designed flow answers a finished scan with frames 02 and 03.
 * Those need normalized data, which is produced by the parsing pipeline behind
 * an endpoint that is still a deferred contract — so a scan stops here. Replace
 * this branch, not the wiring above it.
 *
 * The wording is careful on one point: nothing has been sent, because there is
 * nowhere to send it. Saying "kept on this machine" would be true today and
 * quietly false the day the endpoint lands.
 */
function scanSummary({ nodeCount, truncated, redactionCount }: ScanResult) {
  const read = `Read ${plural(nodeCount, 'element')}${truncated ? ', capped before the end of the page' : ''}.`
  const guarded =
    redactionCount > 0
      ? ` The guard removed ${plural(redactionCount, 'item')} before anything could be sent.`
      : ' The guard found nothing it had to remove.'
  return `${read}${guarded} Nothing has been sent anywhere yet.`
}

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
