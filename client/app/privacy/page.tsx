import type { Metadata } from 'next'
import { CheckCircle, ShieldCheck } from '@phosphor-icons/react/dist/ssr'

import { Footer, Nav, eyebrow, shell } from '@/components/site-chrome'
import { cn } from '@/lib/utils'

/* TODO: two blockers before the Chrome Web Store listing can be submitted —
   the store requires a live privacy policy URL carrying a real contact.
   Defaults below are placeholders, not decisions. */
const CONTACT_EMAIL = 'privacy@boomerang.app'
const LEGAL_ENTITY = 'Boomerang Labs'

const LAST_UPDATED = '9 September 2026'

export const metadata: Metadata = {
  title: 'Privacy — Boomerang',
  description:
    'What Boomerang holds, what it never touches, and exactly which data crosses each boundary.',
}

type Exposure = 'stored' | 'transient' | 'local'

const EXPOSURE: Record<Exposure, string> = {
  /* Same data-only scale as the order badges: this says how exposed a row is,
     never how important it is. */
  stored: 'bg-warn',
  transient: 'bg-warn',
  local: 'bg-calm',
}

const BOUNDARY: { data: string; lives: string; leaves: string; tone: Exposure }[] = [
  {
    data: 'Retailer order page content',
    lives: 'Extension → our server → Bedrock',
    leaves: 'Yes, transiently. Normalized, then the raw page is discarded.',
    tone: 'transient',
  },
  {
    data: 'Return-flow step content',
    lives: 'Extension → our server → Bedrock',
    leaves: 'Only when a configured selector misses.',
    tone: 'transient',
  },
  {
    data: 'Normalized orders, items and deadlines',
    lives: 'Our database, scoped to your account',
    leaves: 'Yes. Stored, so the dashboard works across devices.',
    tone: 'stored',
  },
  {
    data: 'Your Google account identity',
    lives: 'Our database — subject id, email, name, avatar',
    leaves: 'Yes. It is how we know the dashboard is yours.',
    tone: 'stored',
  },
  {
    data: 'Return progress detail and checkpoints',
    lives: 'Your browser (chrome.storage.local)',
    leaves: 'No. Only a one-line status summary is stored.',
    tone: 'local',
  },
  {
    data: 'Label page — tracking number, return address',
    lives: 'Extension only',
    leaves: 'Never. It is not transmitted at all.',
    tone: 'local',
  },
  {
    data: 'Retailer login session',
    lives: 'Your browser only',
    leaves: 'No. We never see your retailer password.',
    tone: 'local',
  },
  {
    data: 'Your email inbox',
    lives: 'Nowhere. We have no access to it.',
    leaves: 'No. No Gmail scope is requested, ever.',
    tone: 'local',
  },
]

const PERMISSIONS = [
  { name: 'activeTab', body: 'Read the current tab, only after you tap Scan.' },
  { name: 'scripting', body: 'Run the return driver in a visible tab.' },
  { name: 'storage', body: 'Keep your in-progress return on this machine.' },
]

const POLICY = [
  {
    title: 'What we collect',
    body: 'The content of retailer order pages you ask us to scan, and the content of return-flow pages when a configured selector fails to match. Both are sent to our server, passed to Amazon Bedrock for extraction, and discarded — we do not keep the raw page. We keep what comes out of it: normalized orders, items, prices, deadlines and return state, stored against your account. Signing in with Google also gives us your Google subject id, email address, display name and avatar.',
  },
  {
    title: 'What we never collect',
    body: 'Your email, from any provider or by any method — there is no Gmail scope in the sign-in request and no inbox scraping. Your retailer username or password. The label page, which carries your tracking number and return address, and is never transmitted. Payment details, which the action vocabulary forbids the agent from typing into.',
  },
  {
    title: 'Where it is stored',
    body: 'Normalized account data lives in our PostgreSQL database. The detailed workflow state of an in-progress return — checkpoints, step history — stays in your browser and is never uploaded; the database holds only the current one-line summary. Each field has exactly one authoritative home, so the two never disagree.',
  },
  {
    title: 'Third parties',
    body: 'Amazon Bedrock receives page content for extraction. Google receives nothing beyond the sign-in exchange that establishes who you are; identity permission does not authorize inbox access. Calendar integration is not part of this version — if it ships, it will ask for a separate grant, and this page will say so before it does.',
  },
  {
    title: 'Retention',
    body: 'Raw and sanitized page content is discarded once extraction returns — it is a transient input, never a stored record. Normalized account data stays until you delete it or close your account. Browser-local state stays until you clear it or uninstall the extension.',
  },
  {
    title: 'Logging',
    body: 'Order contents, item titles, addresses and confirmation numbers are never written to a log at any level, debug included. This is enforced by a redacting formatter rather than by convention. Logs carry a per-request identifier, field presence and validation outcomes — nothing that identifies you.',
  },
  {
    title: 'Your controls',
    body: 'Deleting an order removes it and everything derived from it. Closing your account removes your account data from our database. Uninstalling the extension removes everything held in the browser — and, because the two stores are separate, uninstalling does not silently delete your web account records.',
  },
  {
    title: 'Limited Use',
    body: 'Our handling of user data complies with the Chrome Web Store User Data Policy, including the Limited Use requirements. We do not sell data, we do not transfer it for advertising, and we do not use it to train models.',
  },
]

export default function PrivacyPage() {
  return (
    <>
      <Nav />
      <main className="flex-1">
        <PageHead />
        <Boundary />
        <Permissions />
        <Policy />
      </main>
      <Footer />
    </>
  )
}

function PageHead() {
  return (
    <section className={cn(shell, 'px-6 pt-20 pb-16 md:px-18')}>
      <p className={cn(eyebrow, 'text-accent')}>Privacy</p>
      <h1 className="mt-4 max-w-[16ch] font-display text-[40px] leading-[1.03] font-semibold tracking-[-0.02em] text-ink md:text-[56px]">
        What we hold, what we never touch.
      </h1>
      <p className="mt-6 max-w-[70ch] text-[17px] leading-[1.55] text-ink-muted">
        Boomerang signs you in with Google and keeps your normalized orders so the dashboard works
        across devices. It has no access to your email, from any provider or by any method, and it
        never sees a retailer password. This page states exactly what crosses each boundary,
        including the parts that are less flattering to us.
      </p>
      <p className="mt-5 text-[13px] text-ink-faint">Last updated {LAST_UPDATED}</p>
    </section>
  )
}

function Boundary() {
  return (
    <section className="bg-surface">
      <div className={cn(shell, 'px-6 py-20 md:px-18')}>
        <h2 className="max-w-[20ch] font-display text-[26px] leading-[1.1] font-semibold tracking-[-0.02em] text-ink md:text-[32px]">
          Every piece of data, and where it goes
        </h2>

        <div className="mt-9 overflow-hidden rounded-[14px] border border-line">
          <div className="hidden grid-cols-[1.3fr_1.2fr_1.3fr] gap-6 border-b border-line bg-bg px-6 py-3.5 md:grid">
            {['Data', 'Where it lives', 'Leaves your browser?'].map((h) => (
              <span
                key={h}
                className="text-[12px] font-semibold tracking-[0.1em] text-ink-faint uppercase"
              >
                {h}
              </span>
            ))}
          </div>

          {BOUNDARY.map((row) => (
            <div
              key={row.data}
              className="grid gap-2 border-b border-line px-6 py-4 last:border-b-0 md:grid-cols-[1.3fr_1.2fr_1.3fr] md:gap-6"
            >
              <span className="text-[14px] font-medium text-ink">{row.data}</span>
              <span className="text-[13.5px] text-ink-muted">{row.lives}</span>
              <span className="flex items-start gap-2.5 text-[13.5px] text-ink-muted">
                <span
                  className={cn('mt-1.5 size-[7px] shrink-0 rounded-full', EXPOSURE[row.tone])}
                  aria-hidden
                />
                {row.leaves}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Permissions() {
  return (
    <section className={cn(shell, 'px-6 py-20 md:px-18')}>
      <div className="rounded-[20px] bg-dark px-8 py-10 text-on-dark md:px-12">
        <div className="flex flex-col gap-10 lg:flex-row lg:gap-16">
          <div className="flex-1">
            <h2 className="max-w-[22ch] font-display text-[22px] leading-[1.2] font-semibold md:text-[26px]">
              Three permissions at install. Nothing else.
            </h2>
            <p className="mt-4 max-w-[58ch] text-[14px] leading-[1.6] text-on-dark-muted">
              <code className="text-accent-bright">activeTab</code> only grants access on a user
              gesture, so the extension cannot read a page when it loads. The first run is a tap on
              Scan this page. Standing access for a retailer is requested afterwards, in context,
              once you have seen it work.
            </p>
          </div>

          <ul className="flex w-full flex-col gap-3 lg:max-w-[420px]">
            {PERMISSIONS.map((perm) => (
              <li key={perm.name} className="flex gap-3.5 rounded-[12px] bg-dark-soft px-4 py-3.5">
                <CheckCircle
                  size={18}
                  weight="fill"
                  className="mt-0.5 shrink-0 text-accent-bright"
                />
                <div>
                  <p className="font-mono text-[13.5px] font-medium">{perm.name}</p>
                  <p className="mt-1 text-[12.5px] text-on-dark-muted">{perm.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

function Policy() {
  return (
    <section className="bg-surface">
      <div className={cn(shell, 'px-6 py-20 md:px-18')}>
        <p className={cn(eyebrow, 'text-accent')}>The formal policy</p>
        <h2 className="mt-4 font-display text-[30px] leading-[1.08] font-semibold tracking-[-0.02em] text-ink md:text-[36px]">
          Privacy policy
        </h2>
        <p className="mt-4 max-w-[64ch] text-[15px] leading-[1.55] text-ink-muted">
          This is the policy referenced from the Chrome Web Store listing. If it and the listing
          ever disagree, treat it as a bug and tell us.
        </p>

        <div className="mt-12 grid gap-x-14 gap-y-9 md:grid-cols-2">
          {POLICY.map((section) => (
            <section key={section.title}>
              <h3 className="text-[15.5px] font-semibold text-ink">{section.title}</h3>
              <p className="mt-2 text-[14.5px] leading-[1.6] text-ink-muted">{section.body}</p>
            </section>
          ))}

          <section>
            <h3 className="text-[15.5px] font-semibold text-ink">Contact</h3>
            <p className="mt-2 text-[14.5px] leading-[1.6] text-ink-muted">
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-accent hover:underline">
                {CONTACT_EMAIL}
              </a>{' '}
              · {LEGAL_ENTITY}
            </p>
          </section>
        </div>

        <p className="mt-14 flex items-center gap-2.5 text-[13.5px] text-ink-faint">
          <ShieldCheck size={17} weight="bold" className="text-calm" />
          No Gmail access of any kind. Not the API, not scraping, not now, not in a later version
          without saying so here first.
        </p>
      </div>
    </section>
  )
}
