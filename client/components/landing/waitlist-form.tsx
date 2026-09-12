'use client'

import { useState } from 'react'
import { CheckCircle, EnvelopeSimple } from '@phosphor-icons/react/dist/ssr'
import { Button } from '@/components/ui/button'

/* dev-note: there is no subscribe endpoint yet. This confirms locally so the
   funnel is walkable end to end. Wire to POST /waitlist (or a form service)
   when one exists — or delete it, if Google sign-in (D10) becomes the only
   way in and the waitlist has nothing left to collect. */
export function WaitlistForm() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)

  if (sent) {
    return (
      <div className="flex w-full max-w-117.5 items-center gap-3 rounded-[10px] border border-calm/30 bg-calm-soft px-4 py-4">
        <CheckCircle size={22} weight="fill" className="shrink-0 text-calm" />
        <div>
          <p className="text-[15px] font-semibold text-ink">You&rsquo;re on the list.</p>
          <p className="text-[12.5px] text-ink-muted">
            One email when the extension ships. Nothing else, ever.
          </p>
        </div>
      </div>
    )
  }

  return (
    <form
      className="w-full max-w-117.5"
      onSubmit={(e) => {
        e.preventDefault()
        setSent(true)
      }}
    >
      <div className="flex flex-col gap-2.5 sm:flex-row">
        <label className="flex flex-1 items-center gap-2.5 rounded-[10px] border border-line bg-surface px-4 py-3.75">
          <EnvelopeSimple size={17} className="shrink-0 text-ink-faint" />
          <span className="sr-only">Email address</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-faint"
          />
        </label>
        <Button type="submit" variant="brand" size="xl">
          Notify me
        </Button>
      </div>
      <p className="mt-2.5 text-[12.5px] text-ink-muted">
        One email when the extension ships. Nothing else, ever.
      </p>
    </form>
  )
}
