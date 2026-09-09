import Link from 'next/link'

import { Wordmark } from '@/components/site-chrome'
import { cn } from '@/lib/utils'

/* dev-note: the real value comes from the extension over externally_connectable.
   Flip it to see the disconnected dashboard. */
export const EXTENSION_CONNECTED = true

const TABS = [
  { href: '/dashboard', label: 'Returns' },
  { href: '/dashboard/pickups', label: 'Pickups' },
  { href: '/privacy', label: 'Privacy' },
]

export function AppBar({ current }: { current: string }) {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex w-full max-w-[1296px] items-center justify-between gap-6 px-6 py-4 md:px-10">
        <Link href="/">
          <Wordmark className="text-ink" />
        </Link>

        <nav className="flex items-center gap-5 md:gap-7">
          {TABS.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={tab.href === current ? 'page' : undefined}
              className={cn(
                'text-[14px] transition-colors',
                tab.href === current ? 'font-semibold text-ink' : 'text-ink-muted hover:text-ink',
              )}
            >
              {tab.label}
            </Link>
          ))}
          <ConnectionPill />
        </nav>
      </div>
    </header>
  )
}

function ConnectionPill() {
  const connected = EXTENSION_CONNECTED
  return (
    <span
      className={cn(
        'flex items-center gap-2 rounded-full px-3 py-1.5 text-[12.5px] font-medium',
        connected ? 'bg-calm-soft text-calm' : 'bg-urgent-soft text-urgent',
      )}
    >
      <span
        className={cn('size-[7px] rounded-full', connected ? 'bg-calm' : 'bg-urgent')}
        aria-hidden
      />
      <span className="hidden sm:inline">
        {connected ? 'Extension connected' : 'Extension not detected'}
      </span>
    </span>
  )
}
