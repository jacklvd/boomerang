import type { ButtonHTMLAttributes } from 'react'

import { cn } from './cn'

type Variant = 'primary' | 'ghost'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-on-accent hover:bg-accent/90',
  ghost: 'border border-line bg-surface text-ink hover:bg-bg',
}

/**
 * The two buttons the popup actually has. Deliberately not a port of the
 * client's `cva` button — that one carries seven variants and nine sizes for a
 * marketing site, and a 400px popup has one full-width shape.
 */
export function Button({
  variant = 'primary',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={cn(
        'w-full rounded-[10px] px-[26px] py-[15px] text-[15px] font-semibold transition-colors',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
        'disabled:pointer-events-none disabled:opacity-50',
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  )
}
