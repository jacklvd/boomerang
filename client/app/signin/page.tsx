import type { Metadata } from 'next'
import Link from 'next/link'
import { GoogleLogo } from '@phosphor-icons/react/dist/ssr'

import { Wordmark, shell } from '@/components/site-chrome'

export const metadata: Metadata = {
  title: 'Sign in — Boomerang',
}

export default function SignInPage() {
  return (
    <>
      <header className="border-b border-line bg-surface px-6 py-5 md:px-10">
        <div className={shell}>
          <Wordmark />
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 py-20">
        <div className="w-full max-w-[620px] rounded-[20px] border border-line bg-surface px-8 pt-13 pb-14 text-center md:px-13">
          <h1 className="font-display text-[30px] leading-[1.1] font-semibold tracking-[-0.02em] text-ink md:text-[38px]">
            Sign in to see your returns.
          </h1>
          <p className="mx-auto mt-3.5 max-w-[48ch] text-[15.5px] leading-[1.6] text-ink-muted">
            Your orders and deadlines are kept against your account, so the dashboard works on
            whatever device you open it on.
          </p>

          {/* dev-note: no auth endpoint yet. This goes to the dashboard so the
              funnel is walkable; swap for the Google authorization redirect. */}
          <Link
            href="/dashboard"
            className="mt-8 inline-flex items-center gap-2.5 rounded-[10px] bg-ink px-6.5 py-[15px] text-[15px] font-semibold text-surface transition-colors hover:bg-ink/90"
          >
            <GoogleLogo size={19} weight="bold" />
            Continue with Google
          </Link>

          <p className="mt-7">
            <Link href="/privacy" className="text-[14px] font-semibold text-accent hover:underline">
              Read exactly what crosses the boundary &rarr;
            </Link>
          </p>
        </div>
      </main>
    </>
  )
}
