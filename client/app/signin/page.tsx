import type { Metadata } from 'next'

import { SignInScreen } from '@/components/sign-in-screen'

export const metadata: Metadata = {
  title: 'Sign in — Boomerang',
}

export default function SignInPage() {
  return <SignInScreen />
}
