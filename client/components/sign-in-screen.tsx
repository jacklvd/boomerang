import Link from 'next/link'
import { GoogleLogo } from '@phosphor-icons/react/dist/ssr'

import { Wordmark, shell } from '@/components/site-chrome'

/**
 * The whole signed-out screen, shared by /signin and the dashboard gate so the
 * two cannot drift. Deliberately carries no dashboard nav: every tab it would
 * show leads somewhere the visitor is not entitled to yet, and the extension
 * connection pill describes data they cannot see. One screen, one decision.
 *
 * What the Google grant does and does not cover lives on /privacy.
 */
export function SignInScreen() {
  return (
    <>
      <header className="border-b border-line bg-surface px-6 py-5 md:px-10">
        <div className={shell}>
          <Link href="/">
            <Wordmark />
          </Link>
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

          {/* dev-note: inert — there is no authorization endpoint to send the
              visitor to. It points at /dashboard, which routes straight back
              here while CURRENT_ACCOUNT is null. Flip that fixture to walk the
              signed-in dashboard; swap this href for the Google redirect when
              auth exists. */}
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
