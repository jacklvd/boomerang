import {
  CalendarPlusIcon,
  CheckCircleIcon,
  MapPinIcon,
  QrCodeIcon,
} from '@phosphor-icons/react/dist/ssr'

import { formatDate } from '@/src/model/read-order'
import type { EphemeralOutcome, TerminalOutcome } from '@/src/model/outcome'
import { Button } from './button'
import { Heading, Notice } from './primitives'

/**
 * Frame 09 — the retailer produced a QR code or a label.
 *
 * A QR drop-off is a finished return, not a failure: no printer, nothing to
 * stick on a box. The screen says so because the alternative reading — that
 * something went wrong and you now have homework — is the obvious one.
 *
 * Everything on this screen except the state comes from the page the user is
 * already looking at, and none of it is kept. The code itself is rendered from
 * the retailer's own page; there is no field on `EphemeralOutcome` to hold its
 * payload, so there is nothing here that could be written down by accident.
 */
export function OutcomeReady({
  outcome,
  details,
  onAddReminder,
  onSaveCode,
}: {
  outcome: TerminalOutcome
  details: EphemeralOutcome
  onAddReminder: () => void
  onSaveCode: () => void
}) {
  const isQr = outcome === 'qr_ready'

  return (
    <>
      <span className="flex w-fit items-center gap-2 rounded-full bg-calm-soft px-3 py-1.5">
        <CheckCircleIcon size={12} weight="fill" className="text-calm" />
        <span className="text-[11.5px] font-semibold tracking-[0.06em] text-calm uppercase">
          Return accepted
        </span>
      </span>

      <Heading
        title={isQr ? 'Show this at the counter' : 'Your label is ready'}
        body={
          isQr
            ? 'The retailer issued a QR drop-off. No printer, no label to stick on.'
            : 'The retailer issued a printable label. Print it and attach it to the parcel.'
        }
      />

      <div className="flex flex-col items-center gap-3 rounded-[10px] bg-surface p-5">
        {/* The retailer drew this. Rendered from their page, never captured —
            see the note on EphemeralOutcome. */}
        <span
          role="img"
          aria-label={details.artifactAltText}
          className="flex size-[128px] items-center justify-center rounded-[6px] bg-bg"
        >
          <QrCodeIcon size={64} className="text-ink-faint" />
        </span>
        {details.reference && (
          <span className="font-mono text-[12.5px] tracking-[0.04em] text-ink-muted">
            {details.reference}
          </span>
        )}
      </div>

      {details.dropOff && (
        <div className="flex gap-3 rounded-[10px] bg-surface p-3.5">
          <MapPinIcon size={15} className="mt-0.5 shrink-0 text-ink-faint" />
          <span className="flex flex-col gap-0.5">
            <span className="text-[13px] font-semibold text-ink">
              {details.dropOff.name} · {details.dropOff.distance}
            </span>
            <span className="text-[12.5px] text-ink-muted">
              {details.dropOffBy && `Drop off by ${formatDate(details.dropOffBy)}. `}
              {details.dropOff.note}
            </span>
          </span>
        </div>
      )}

      <div className="flex flex-col gap-2.5">
        <Button onClick={onAddReminder}>
          <CalendarPlusIcon size={16} weight="bold" />
          Add a reminder
        </Button>
        <Button variant="ghost" onClick={onSaveCode}>
          {isQr ? 'Save the QR code' : 'Open the label'}
        </Button>
      </div>

      <Notice tone="quiet">
        The code is the retailer's and lives on their page. We record that this return reached{' '}
        {isQr ? 'a QR code' : 'a label'} — nothing more.
      </Notice>
    </>
  )
}
