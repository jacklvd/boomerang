import { SignInScreen } from '@/components/sign-in-screen'
import { CURRENT_ACCOUNT } from '@/lib/account'

/**
 * Gates every dashboard route on the account, not just the page that remembers
 * to check. D8 makes these views read account-scoped server data, so without a
 * signed-in account there is nothing they are entitled to render.
 *
 * dev-note: the real gate belongs in middleware or a server session lookup once
 * an auth endpoint exists. Rendering the prompt rather than redirecting keeps
 * this working under either answer to the export/standalone question.
 */
export default function DashboardLayout({ children }: LayoutProps<'/dashboard'>) {
  return CURRENT_ACCOUNT ? children : <SignInScreen />
}
