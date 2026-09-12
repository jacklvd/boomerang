import Link from 'next/link'
import { ArrowArcLeft } from '@phosphor-icons/react/dist/ssr'

import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/* TODO: point at the Chrome Web Store listing once the extension is published.
   Until then the install funnel falls back to the waitlist — there is no second
   distribution channel to fall back to. */
export const CHROME_STORE_URL = '/#waitlist'

/* Root-relative so the same nav works from /privacy, not just the landing page. */
export const NAV_LINKS = [
  { href: '/#how-it-works', label: 'How it works' },
  { href: '/#pickup', label: 'Pickup' },
  { href: '/privacy', label: 'Privacy' },
]

export const shell = 'mx-auto w-full max-w-[1296px]'
export const eyebrow = 'text-[12.5px] font-semibold tracking-[0.12em] uppercase'

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <ArrowArcLeft size={22} weight="bold" className="text-accent" />
      <span className="font-display text-[17px] font-semibold">Boomerang</span>
    </span>
  )
}

export function Nav() {
  return (
    <header className="sticky top-0 z-50 border-b border-line/70 bg-bg/85 backdrop-blur">
      <div className={cn(shell, 'flex items-center justify-between px-6 py-5 md:px-18')}>
        <Link href="/">
          <Wordmark className="text-ink" />
        </Link>
        <nav className="flex items-center gap-6 md:gap-8.5">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="hidden text-[14.5px] text-ink-muted transition-colors hover:text-ink sm:block"
            >
              {link.label}
            </Link>
          ))}
          <Link
            href={CHROME_STORE_URL}
            className={cn(
              buttonVariants({ variant: 'brand', size: 'xl' }),
              'px-5 py-2.5 text-[14px]',
            )}
          >
            Add to Chrome
          </Link>
        </nav>
      </div>
    </header>
  )
}

export function Footer() {
  return (
    <footer className="bg-dark text-on-dark">
      <div className={cn(shell, 'px-6 py-14 md:px-18')}>
        <div className="flex flex-wrap items-center justify-between gap-8">
          <Wordmark />
          <nav className="flex flex-wrap gap-8">
            {[...NAV_LINKS, { href: CHROME_STORE_URL, label: 'Chrome Web Store' }].map((link) => (
              <Link
                key={link.label}
                href={link.href}
                className="text-[14px] text-on-dark-muted transition-colors hover:text-white"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="mt-9 flex flex-wrap gap-x-10 gap-y-2 text-[12.5px] text-on-dark-muted">
          <p>&copy; 2026 Boomerang. Return windows are estimates, not guarantees.</p>
          <p>Not affiliated with the United States Postal Service.</p>
        </div>
      </div>
    </footer>
  )
}
