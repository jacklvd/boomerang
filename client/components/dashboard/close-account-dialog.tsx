'use client'

import { useState } from 'react'
import { Browser, Trash, Warning } from '@phosphor-icons/react/dist/ssr'

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'

/**
 * D9 splits durable account state from local execution state, so closing the
 * account only reaches one of the two stores. Both panels are the point: a
 * confirm that implied it deleted everything would contradict what /privacy
 * promises about the two stores being separate.
 */
const CONSEQUENCES = [
  {
    icon: Trash,
    tone: 'bg-urgent-soft text-urgent',
    title: 'Removed from our database',
    body: 'Your Google identity, your normalized orders, deadlines, values and return state.',
  },
  {
    icon: Browser,
    tone: 'bg-bg text-ink-faint',
    title: 'Left in your browser',
    body: 'The extension keeps what it holds locally, including any return in progress. Uninstall it separately.',
  },
]

const CONFIRM_WORD = 'CLOSE'

export function CloseAccountDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [confirm, setConfirm] = useState('')

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setConfirm('')
        onOpenChange(next)
      }}
    >
      <AlertDialogContent className="block rounded-[20px] bg-surface p-10 ring-0 data-[size=default]:max-w-[580px] data-[size=default]:sm:max-w-[580px]">
        <div className="flex items-start gap-4">
          <span className="flex size-11.5 shrink-0 items-center justify-center rounded-full bg-urgent-soft">
            <Warning size={22} weight="bold" className="text-urgent" />
          </span>
          <div className="min-w-0">
            <AlertDialogTitle className="font-display text-[24px] leading-[1.15] font-semibold tracking-[-0.02em] text-ink">
              Close your Boomerang account?
            </AlertDialogTitle>
            <AlertDialogDescription className="mt-2 text-[14.5px] leading-[1.55] text-ink-muted">
              This removes your account and everything we derived from your orders. It cannot be
              undone.
            </AlertDialogDescription>
          </div>
        </div>

        <ul className="mt-6.5 flex flex-col gap-2.5">
          {CONSEQUENCES.map(({ icon: Icon, tone, title, body }) => (
            <li key={title} className={`flex gap-3.5 rounded-[13px] p-4.5 ${tone}`}>
              <Icon size={17} weight="bold" className="mt-0.5 shrink-0" />
              <div className="min-w-0">
                <p className="text-[13.5px] font-bold text-ink">{title}</p>
                <p className="mt-1 text-[13px] leading-[1.5] text-ink-muted">{body}</p>
              </div>
            </li>
          ))}
        </ul>

        <div className="mt-6.5">
          <label htmlFor="close-confirm" className="text-[13px] font-semibold text-ink-muted">
            Type {CONFIRM_WORD} to confirm
          </label>
          <input
            id="close-confirm"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder={CONFIRM_WORD}
            autoComplete="off"
            className="mt-2 w-full rounded-[10px] border border-line bg-bg px-4 py-3 text-[14px] tracking-[0.06em] text-ink outline-none placeholder:text-ink-faint focus:border-accent"
          />
        </div>

        <div className="mt-6.5 flex justify-end gap-2.5">
          <Button variant="brandOutline" size="xl" onClick={() => onOpenChange(false)}>
            Keep my account
          </Button>
          {/* dev-note: no DELETE /account yet — this only closes the dialog. */}
          <Button
            size="xl"
            disabled={confirm !== CONFIRM_WORD}
            className="bg-urgent text-on-accent hover:bg-urgent/90"
            onClick={() => onOpenChange(false)}
          >
            Close account
          </Button>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  )
}
