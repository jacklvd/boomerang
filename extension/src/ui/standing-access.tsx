import { CheckIcon, CursorClickIcon, LightningIcon, XIcon } from '@phosphor-icons/react/dist/ssr'

import { Button } from './button'

/**
 * Frame E2 — the offer to skip the tap on one retailer.
 *
 * Shown only after a scan has worked, never at install. The two rows are the
 * substance: the user is being asked to trade a gesture for a standing
 * permission, and the screen has to show what changes and what does not.
 *
 * The scope list is the part that must stay honest. It names the two things
 * that are *not* being granted alongside the one that is, because "allow for
 * this site" means nothing to someone who cannot see what the alternative
 * would have been.
 */
export function StandingAccess({
  hostname,
  onAllow,
  onDecline,
  pending = false,
  error,
}: {
  hostname: string
  onAllow: () => void
  onDecline: () => void
  pending?: boolean
  error?: string
}) {
  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 className="font-display text-[19px] leading-tight font-semibold text-ink">
          Skip the tap next time?
        </h1>
        <p className="text-[13.5px] leading-[1.45] text-ink-muted">
          Allow Boomerang to recognise order pages on this one retailer automatically.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <Compare
          icon={<CursorClickIcon size={18} className="text-ink-faint" />}
          title="Now — you tap Scan"
          body="Nothing is read until you open the popup and ask."
        />
        <Compare
          highlighted
          icon={<LightningIcon size={18} weight="fill" className="text-accent" />}
          title={`With access to ${hostname}`}
          body="We spot the order page and show the badge. Still this one site only."
        />
      </div>

      <ul className="flex flex-col gap-1.5">
        <Scope included>{hostname} only</Scope>
        <Scope>Every other site you visit</Scope>
        <Scope>All sites, ever</Scope>
      </ul>

      {error && (
        <p className="rounded-[10px] bg-urgent-soft px-3 py-2.5 text-[12.5px] text-urgent">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-2.5">
        <Button onClick={onAllow} disabled={pending}>
          {pending ? 'Waiting for Chrome…' : `Allow for ${hostname}`}
        </Button>
        <Button variant="ghost" onClick={onDecline}>
          Keep asking each time
        </Button>
      </div>

      <p className="text-[12px] leading-[1.45] text-ink-faint">
        Revoke it in Chrome whenever you like. We never request access to all sites.
      </p>
    </>
  )
}

function Compare({
  icon,
  title,
  body,
  highlighted = false,
}: {
  icon: React.ReactNode
  title: string
  body: string
  highlighted?: boolean
}) {
  return (
    <div
      className={`flex gap-3 rounded-[10px] border p-3 ${
        highlighted ? 'border-accent bg-accent-soft' : 'border-line bg-surface'
      }`}
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="flex flex-col gap-1">
        <span className="text-[13px] font-semibold text-ink">{title}</span>
        <span className="text-[12.5px] leading-[1.4] text-ink-muted">{body}</span>
      </div>
    </div>
  )
}

function Scope({ children, included = false }: { children: React.ReactNode; included?: boolean }) {
  const Icon = included ? CheckIcon : XIcon
  return (
    <li className="flex items-center gap-2 text-[12.5px] text-ink-muted">
      <Icon size={14} weight="bold" className={included ? 'text-calm' : 'text-urgent'} />
      <span>{children}</span>
    </li>
  )
}
