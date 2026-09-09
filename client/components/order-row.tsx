import { cn } from '@/lib/utils'
import { URGENCY_CLASSES, urgencyOf, type Order } from '@/lib/orders'

export function OrderRow({ order, className }: { order: Order; className?: string }) {
  const tone = URGENCY_CLASSES[urgencyOf(order.daysLeft)]

  return (
    <div className={cn('flex items-center gap-4 rounded-[14px] bg-surface px-4 py-3.5', className)}>
      <div className="size-11 shrink-0 rounded-[9px] bg-[#e6e0d5]" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14.5px] font-semibold text-ink">{order.title}</p>
        <p className="truncate text-[12.5px] text-ink-muted">
          {order.retailer} · delivered {order.deliveredOn} · ${order.price.toFixed(2)}
        </p>
      </div>
      <span
        className={cn(
          'flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-semibold',
          tone.badge,
          tone.text,
        )}
      >
        <span className={cn('size-1.75 rounded-full', tone.dot)} aria-hidden />
        {order.daysLeft} days left
      </span>
    </div>
  )
}
