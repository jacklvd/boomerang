import { SignInScreen } from '@/components/sign-in-screen'
import { CURRENT_ACCOUNT } from '@/lib/account'

/**
 * Renders the signed-out screen for every route under /dashboard, so one added
 * later gets it without having to remember to ask.
 *
 * This is a UI state, not an authorization boundary, and it must not be
 * mistaken for one. Next prerenders the page segment even when this layout
 * discards `children`, so with CURRENT_ACCOUNT null the order fixture is absent
 * from the visible DOM but still present in the RSC flight payload of the same
 * HTML — hidden, not withheld. Confirmed by grepping the built
 * .next/server/app/dashboard.html for order titles.
 *
 * Real gating belongs at the data layer: the server does not answer GET /orders
 * for an unauthenticated request, so there is nothing to render or serialize.
 * That arrives with auth. Nothing in this file substitutes for it.
 */
export default function DashboardLayout({ children }: LayoutProps<'/dashboard'>) {
  return CURRENT_ACCOUNT ? children : <SignInScreen />
}
