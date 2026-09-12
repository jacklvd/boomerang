'use client'

import { useState } from 'react'
import Link from 'next/link'
import { CaretDown, Gear, SignOut, Trash } from '@phosphor-icons/react/dist/ssr'

import { CloseAccountDialog } from '@/components/dashboard/close-account-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { CURRENT_ACCOUNT, initialsOf } from '@/lib/account'

export function AccountMenu() {
  const [closing, setClosing] = useState(false)
  const account = CURRENT_ACCOUNT

  if (!account) {
    return (
      <Link
        href="/signin"
        className="rounded-[9px] bg-ink px-3.5 py-2 text-[13px] font-semibold text-surface hover:bg-ink/90"
      >
        Sign in
      </Link>
    )
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          className="flex items-center gap-2 rounded-full p-0.5 outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          aria-label={`Account menu for ${account.name}`}
        >
          <span className="flex size-[30px] items-center justify-center rounded-full bg-accent text-[13px] font-bold text-on-accent">
            {initialsOf(account.name)}
          </span>
          <CaretDown size={13} className="text-ink-faint" />
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" className="w-[268px] rounded-[14px] p-0">
          <div className="border-b border-line px-4.5 py-4">
            <p className="text-[14px] font-bold text-ink">{account.name}</p>
            <p className="text-[12.5px] text-ink-faint">{account.email}</p>
          </div>

          <div className="p-2">
            <DropdownMenuItem className="gap-2.5">
              <Gear size={16} className="text-ink-faint" />
              Account settings
            </DropdownMenuItem>
            <DropdownMenuItem className="gap-2.5">
              <SignOut size={16} className="text-ink-faint" />
              Sign out
            </DropdownMenuItem>
          </div>

          <DropdownMenuSeparator className="my-0" />

          <div className="p-2">
            <DropdownMenuItem
              className="gap-2.5 text-urgent focus:text-urgent"
              onClick={() => setClosing(true)}
            >
              <Trash size={16} className="text-urgent" />
              Close account
            </DropdownMenuItem>
          </div>
        </DropdownMenuContent>
      </DropdownMenu>

      <CloseAccountDialog open={closing} onOpenChange={setClosing} />
    </>
  )
}
