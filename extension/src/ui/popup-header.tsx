import { ArrowArcLeftIcon, XIcon } from '@phosphor-icons/react/dist/ssr'

/**
 * The bar every popup frame shares. `status` is the only thing that varies
 * across the sixteen designed screens — START, STEP 3 OF 6, WORKING, STOPPED —
 * so it is a prop rather than sixteen headers.
 *
 * `onClose` is required rather than optional. The close button always renders,
 * so an optional handler buys nothing except the chance to ship a button that
 * silently does nothing — which is exactly what frame 01 shipped with.
 */
export function PopupHeader({ status, onClose }: { status: string; onClose: () => void }) {
  return (
    <header className="flex items-center justify-between border-b border-line bg-surface px-4 py-3">
      <span className="flex items-center gap-2">
        <ArrowArcLeftIcon size={18} weight="bold" className="text-accent" />
        <span className="font-display text-[15px] font-semibold text-ink">Boomerang</span>
      </span>
      <span className="flex items-center gap-3">
        <span className="text-[11px] font-semibold tracking-[0.12em] text-ink-faint uppercase">
          {status}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="text-ink-faint transition-colors hover:text-ink"
        >
          <XIcon size={15} weight="bold" />
        </button>
      </span>
    </header>
  )
}
