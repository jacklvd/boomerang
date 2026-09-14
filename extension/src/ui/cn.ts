import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Same helper as the client's `@/lib/utils`. Kept local for the same reason
 *  the tokens are: the two workspaces do not share a package graph. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
