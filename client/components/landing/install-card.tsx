import Link from 'next/link'
import { ArrowArcLeft, ShieldCheck } from '@phosphor-icons/react/dist/ssr'

import { CHROME_STORE_URL } from '@/components/site-chrome'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function InstallCard({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'flex w-full max-w-120 items-center gap-4 rounded-[16px] border border-line bg-surface p-4.5 text-left',
        className,
      )}
    >
      <span className="flex size-14 shrink-0 items-center justify-center rounded-[15px] bg-accent-soft text-accent">
        <ArrowArcLeft size={27} weight="bold" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-bold text-ink">Boomerang &mdash; Returns Concierge</p>
        <p className="text-[12.5px] text-ink-muted">Chrome Web Store · Free · No account</p>
        <p className="mt-1.5 flex items-center gap-1.5 text-[12.5px] text-calm">
          <ShieldCheck size={14} weight="bold" />
          Asks for page access only when you tap Scan
        </p>
      </div>
      <Link
        href={CHROME_STORE_URL}
        className={cn(buttonVariants({ variant: 'brand', size: 'xl' }), 'px-5 py-3 text-[14px]')}
      >
        Install
      </Link>
    </div>
  )
}
