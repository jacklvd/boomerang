import {
  ArrowArcLeft,
  CalendarCheck,
  Check,
  Database,
  EnvelopeSimpleOpen,
  Key,
  MapPin,
  Package,
  Plus,
  Scales,
  ShieldCheck,
  Truck,
} from '@phosphor-icons/react/dist/ssr'

import Link from 'next/link'

import { Button, buttonVariants } from '@/components/ui/button'
import { OrderRow } from '@/components/order-row'
import {
  ArtCalendar,
  ArtOneClick,
  ArtOpenOrders,
  ArtPickup,
  ArtRank,
} from '@/components/landing/flow-art'
import { WaitlistForm } from '@/components/landing/waitlist-form'
import { CHROME_STORE_URL, Footer, Nav, eyebrow, shell } from '@/components/site-chrome'
import { MOCK_ORDERS, totalAtRisk } from '@/lib/orders'
import { cn } from '@/lib/utils'

export default function Home() {
  return (
    <>
      <Nav />
      <main className="flex-1">
        <Hero />
        <HowItWorks />
        <Pickup />
        <Privacy />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </>
  )
}

function Hero() {
  const atRisk = totalAtRisk(MOCK_ORDERS)

  return (
    <section className={cn(shell, 'px-6 pt-16 pb-22 md:px-18')}>
      <div className="flex flex-col items-center gap-14 lg:flex-row">
        <div className="flex-1">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-1.5">
            <span className="size-1.75 rounded-full bg-urgent" aria-hidden />
            <span className="text-[12.5px] font-medium text-ink-muted">
              ${atRisk.toFixed(0)} of returnable items expire this month
            </span>
          </span>

          <h1 className="mt-6 max-w-[13ch] font-display text-[44px] leading-[1.02] font-semibold tracking-[-0.02em] text-ink md:text-[66px]">
            Never eat the cost of a return you meant to make.
          </h1>

          <p className="mt-6 max-w-[52ch] text-[17px] leading-[1.55] text-ink-muted">
            Boomerang notices what you bought, counts down every return window, then drives the
            whole return for you &mdash; printed label, free USPS pickup at your door, calendar
            reminder. It never touches your email.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-5">
            <a href={CHROME_STORE_URL} className={buttonVariants({ variant: 'brand', size: 'xl' })}>
              Add to Chrome &mdash; free
            </a>
            <a href="#waitlist" className="text-[15px] text-ink-muted underline hover:text-ink">
              or join the waitlist
            </a>
          </div>

          <ul className="mt-8 flex flex-wrap gap-x-7 gap-y-3">
            {['No email access', 'No retailer password', 'Nothing to configure'].map((item) => (
              <li key={item} className="flex items-center gap-2 text-[13.5px] text-ink-muted">
                <Check size={15} weight="bold" className="text-accent" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <PopupMock />
      </div>
    </section>
  )
}

function PopupMock() {
  return (
    <div className="w-full max-w-113 shrink-0 rounded-[20px] border border-line bg-surface shadow-[0_24px_60px_-30px_rgba(26,25,23,0.35)]">
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <span className="flex items-center gap-2.5 text-ink">
          <ArrowArcLeft size={18} weight="bold" className="text-accent" />
          <span className="text-[14.5px] font-semibold">{MOCK_ORDERS.length} returns open</span>
        </span>
        <span className="text-[12.5px] text-ink-faint">Sorted by deadline</span>
      </div>

      <div className="flex flex-col gap-2 bg-bg p-3">
        {MOCK_ORDERS.map((order) => (
          <OrderRow key={order.id} order={order} className="border border-line" />
        ))}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-4">
        <span className="text-[12.5px] text-ink-faint">Windows are estimates, not guarantees.</span>
        <Button variant="brand" size="xl" className="px-4 py-2.5 text-[13px]">
          Return the coat
        </Button>
      </div>
    </div>
  )
}

const STEPS = [
  {
    n: '01',
    art: ArtOpenOrders,
    title: 'You open your orders',
    body: 'Any retailer page you are already signed into. Nothing is installed on their side.',
  },
  {
    n: '02',
    art: ArtRank,
    title: 'We rank what is closing',
    body: 'Every order gets a return-by date and a place in the queue. Soonest first.',
  },
  {
    n: '03',
    art: ArtOneClick,
    title: 'One click starts the return',
    body: "The agent walks the retailer's flow for you and pauses at anything irreversible.",
  },
  {
    n: '04',
    art: ArtPickup,
    title: 'Label printed, box collected',
    body: 'Free USPS pickup at your door — no drop-off, no line, no postage to buy.',
  },
  {
    n: '05',
    art: ArtCalendar,
    title: 'Reminder on your calendar',
    body: 'A prefilled calendar event so the box is out on the right day.',
  },
]

function HowItWorks() {
  return (
    <section id="how-it-works" className="scroll-mt-20 bg-surface">
      <div className={cn(shell, 'px-6 py-22 md:px-18 md:py-24')}>
        <div className="max-w-190">
          <p className={cn(eyebrow, 'text-accent')}>How it works</p>
          <h2 className="mt-3.5 font-display text-[32px] leading-[1.08] font-semibold tracking-[-0.02em] text-ink md:text-[44px]">
            Five steps. You do the first one.
          </h2>
          <p className="mt-3.5 text-[16.5px] leading-[1.55] text-ink-muted">
            Open your orders page once. Boomerang handles the rest, and stops to ask you before
            anything it cannot undo.
          </p>
        </div>

        <ol className="mt-14 grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map(({ n, art: Art, title, body }) => (
            <li key={n} className="relative">
              <Art />
              <p className="mt-4 font-mono text-[12px] font-semibold text-accent">{n}</p>
              <h3 className="mt-1.5 text-[16px] font-semibold text-ink">{title}</h3>
              <p className="mt-1.5 text-[13.5px] leading-normal text-ink-muted">{body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

const PICKUP_FACTS = [
  {
    icon: Truck,
    title: 'It is a day, not a time window',
    body: 'Pickup happens on the normal delivery round, so we name the day USPS gives us and never promise an hour.',
  },
  {
    icon: Package,
    title: 'The postage on the box must be USPS',
    body: 'A printed UPS or FedEx label will not be collected, whatever it cost. We check whose postage it is before offering pickup.',
  },
  {
    icon: MapPin,
    title: 'Your address has to be eligible',
    body: 'We check every time, never from memory. If the answer is no, you get drop-off options with prices, not a surprise charge.',
  },
  {
    icon: Scales,
    title: 'We never pick the paid option for you',
    body: 'Where the retailer offers a choice, you see every method and what it costs. Buying a paid label out of your refund is the one thing we will not do.',
  },
]

function Pickup() {
  return (
    <section id="pickup" className="scroll-mt-20">
      <div className={cn(shell, 'flex flex-col gap-14 px-6 py-24 md:px-18 lg:flex-row lg:gap-18')}>
        <div className="flex-1">
          <p className={cn(eyebrow, 'text-ink-faint')}>The part people don&rsquo;t believe</p>
          <h2 className="mt-3.5 max-w-[15ch] font-display text-[34px] leading-[1.06] font-semibold tracking-[-0.02em] text-ink md:text-[46px]">
            A postal carrier collects the box from your door. For free.
          </h2>
          <p className="mt-6 max-w-[52ch] text-[16.5px] leading-[1.55] text-ink-muted">
            USPS Carrier Pickup is a real service almost nobody uses, because almost nobody knows it
            exists. Your carrier is already walking to your door. Boomerang just asks them to take
            the box back with them.
          </p>
          <p className="mt-4 max-w-[52ch] text-[16.5px] leading-[1.55] text-ink-muted">
            No drop-off. No queue. No postage to buy. Here is exactly when it works, and when it
            does not.
          </p>

          <div className="mt-8 max-w-[52ch] rounded-[14px] border border-accent-soft bg-accent-soft/50 p-5">
            <p className="flex items-center gap-2 text-[11.5px] font-semibold tracking-widest text-accent uppercase">
              <CalendarCheck size={16} weight="bold" />
              What we would tell you
            </p>
            <p className="mt-3 text-[16.5px] leading-[1.45] font-medium text-ink">
              Your carrier will collect it on Wednesday, 2 September.
            </p>
            <p className="mt-2 text-[12.5px] text-ink-muted">
              The day USPS gave us. Not a guess, and never a two-hour window.
            </p>
          </div>
        </div>

        <ul className="flex w-full max-w-130 flex-col gap-3.5">
          {PICKUP_FACTS.map(({ icon: Icon, title, body }) => (
            <li key={title} className="flex gap-4 rounded-[14px] border border-line bg-surface p-5">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-[11px] bg-accent-soft text-accent">
                <Icon size={20} weight="bold" />
              </span>
              <div>
                <h3 className="text-[15.5px] font-semibold text-ink">{title}</h3>
                <p className="mt-1.5 text-[13.5px] leading-normal text-ink-muted">{body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

const CLAIMS = [
  {
    icon: Key,
    title: 'Google sign-in, and nothing past it.',
    body: 'You sign in with Google so we know whose returns these are. That grant carries your identity alone — no inbox scope, no Drive, no calendar — and it gives our server no way into any retailer page.',
  },
  {
    icon: EnvelopeSimpleOpen,
    title: 'No Gmail. Not the API, not scraping.',
    body: 'Order data comes from retailer pages you are already signed into, read in your own browser session. We never see your retailer password, and no Gmail scope is requested, ever.',
  },
  {
    icon: Database,
    title: 'We keep the summary, never the session.',
    body: 'We store normalized orders, deadlines and return state against your account, so the dashboard works on any device. The step-by-step state of a return in progress stays in your browser and is never uploaded.',
  },
]

function Privacy() {
  return (
    <section id="privacy" className="scroll-mt-20 bg-dark text-on-dark">
      <div className={cn(shell, 'px-6 py-24 md:px-18 md:py-26')}>
        <div className="flex flex-col gap-10 lg:flex-row lg:gap-16">
          <div className="flex-1">
            <p className={cn(eyebrow, 'text-accent-bright')}>Privacy by architecture</p>
            <h2 className="mt-3.5 max-w-[16ch] font-display text-[34px] leading-[1.06] font-semibold tracking-[-0.02em] md:text-[46px]">
              We cannot read your email. Not by policy &mdash; by design.
            </h2>
          </div>
          <p className="max-w-[46ch] flex-1 self-end text-[15.5px] leading-[1.6] text-on-dark-muted">
            Most extensions ask you to trust a promise. Boomerang removes the capability instead
            &mdash; signing in tells us who you are, and nothing in that grant can reach your inbox
            or your retailer accounts while you are away.
          </p>
        </div>

        <ul className="mt-14 grid gap-5 md:grid-cols-3">
          {CLAIMS.map(({ icon: Icon, title, body }) => (
            <li key={title} className="rounded-[16px] bg-dark-soft p-6">
              <span className="flex size-11 items-center justify-center rounded-[12px] bg-white/5 text-accent-bright">
                <Icon size={22} weight="bold" />
              </span>
              <h3 className="mt-5 text-[17px] leading-tight font-semibold">{title}</h3>
              <p className="mt-2.5 text-[14px] leading-[1.55] text-on-dark-muted">{body}</p>
            </li>
          ))}
        </ul>

        <div className="mt-11 flex flex-wrap items-center gap-6">
          <span className="flex items-center gap-2.5 text-[13.5px] text-on-dark-muted">
            <ShieldCheck size={18} weight="bold" className="text-accent-bright" />
            The extension asks for activeTab, scripting and storage. Nothing else at install.
          </span>
          <Link
            href="/privacy"
            className="text-[14.5px] font-medium text-accent-bright hover:underline"
          >
            Read exactly what crosses the boundary &rarr;
          </Link>
        </div>
      </div>
    </section>
  )
}

const FAQS = [
  {
    q: 'Does Boomerang read my email?',
    a: 'No. There is no Gmail access of any kind — not the API, not scraping — and no Gmail scope is ever requested. Signing in with Google establishes who you are; it does not authorize inbox access. Order data comes from retailer pages you are already viewing.',
  },
  {
    q: 'What happens on the very first run?',
    a: 'Nothing until you ask. The extension cannot read a page on load; it can only act after you tap Scan this page. Standing access for that retailer is requested afterwards, once you have seen it work.',
  },
  {
    q: 'Is the USPS pickup really free?',
    a: "Yes, when the box carries prepaid USPS postage — it rides the carrier's normal delivery round. If your address is not eligible we say so and show drop-off options with their prices.",
  },
  {
    q: 'What if the retailer only offers a paid label?',
    a: 'You see every method and what each one costs, and we stop there. We will never buy a paid label out of your refund just to make our own pickup step work.',
  },
  {
    q: 'Are the return dates guaranteed?',
    a: 'No. Windows are inferred from the order page, and retailers vary policy by category, sale status and membership tier. Treat a date as a prompt to act, never a promise.',
  },
  {
    q: 'What happens to my data if I uninstall?',
    a: 'Uninstalling removes everything the extension holds in your browser, including the detailed state of any return in progress. It does not close your web account — normalized orders live in our database so the dashboard works elsewhere. Close the account from the dashboard to remove those.',
  },
]

function Faq() {
  return (
    <section className="bg-surface">
      <div className={cn(shell, 'flex flex-col gap-12 px-6 py-24 md:px-18 lg:flex-row lg:gap-22')}>
        <div className="w-full max-w-100">
          <p className={cn(eyebrow, 'text-accent')}>Questions</p>
          <h2 className="mt-4 font-display text-[32px] leading-[1.08] font-semibold tracking-[-0.02em] text-ink md:text-[42px]">
            The ones worth asking.
          </h2>
          <p className="mt-4 text-[15px] leading-[1.55] text-ink-muted">
            Including the ones with an inconvenient answer. If something here changes, this page
            changes with it.
          </p>
        </div>

        {/* Native <details> — an accordion is one of the few widgets the platform
            already ships, keyboard and screen-reader behaviour included. */}
        <div className="flex-1">
          {FAQS.map(({ q, a }) => (
            <details key={q} className="group border-b border-line">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5.5">
                <span className="text-[17px] font-medium text-ink">{q}</span>
                <Plus
                  size={20}
                  className="shrink-0 text-ink-faint transition-transform group-open:rotate-45"
                />
              </summary>
              <p className="max-w-[62ch] pb-6 text-[14.5px] leading-[1.6] text-ink-muted">{a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}

function FinalCta() {
  return (
    <section id="waitlist" className="scroll-mt-20">
      <div className={cn(shell, 'flex flex-col items-center px-6 py-26 text-center md:px-18')}>
        <h2 className="max-w-[18ch] font-display text-[36px] leading-[1.05] font-semibold tracking-[-0.02em] text-ink md:text-[50px]">
          Something in your house is still returnable.
        </h2>
        <p className="mt-4.5 max-w-[56ch] text-[17px] leading-[1.55] text-ink-muted">
          Install it once, open your orders page, and find out what you are still owed.
        </p>

        <div className="mt-10 flex w-full max-w-120 items-center gap-4 rounded-[16px] border border-line bg-surface p-4.5 text-left">
          <span className="flex size-14 shrink-0 items-center justify-center rounded-[15px] bg-accent-soft text-accent">
            <ArrowArcLeft size={27} weight="bold" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-bold text-ink">Boomerang &mdash; Returns Concierge</p>
            <p className="text-[12.5px] text-ink-muted">
              Chrome Web Store · Free · Sign in with Google
            </p>
            <p className="mt-1.5 flex items-center gap-1.5 text-[12.5px] text-calm">
              <ShieldCheck size={14} weight="bold" />
              Asks for page access only when you tap Scan
            </p>
          </div>
          <a
            href={CHROME_STORE_URL}
            className={cn(
              buttonVariants({ variant: 'brand', size: 'xl' }),
              'px-5 py-3 text-[14px]',
            )}
          >
            Install
          </a>
        </div>

        <div className="mt-10 flex w-full max-w-130 items-center gap-4.5">
          <span className="h-px flex-1 bg-line" />
          <span className="text-[13px] font-medium tracking-[0.08em] text-ink-faint uppercase">
            Not on Chrome yet?
          </span>
          <span className="h-px flex-1 bg-line" />
        </div>

        <div className="mt-7 flex w-full justify-center text-left">
          <WaitlistForm />
        </div>
      </div>
    </section>
  )
}
