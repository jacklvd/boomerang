/**
 * Which designed screen to render instead of the live flow.
 *
 * Frames 02 and 03 need an extractor that does not exist, and the live popup
 * must not reach them: showing a parsed order after a real scan would claim we
 * read it off the page when the data is a fixture. This is how you look at them
 * without the popup lying to anyone who is not you.
 *
 * dev-note: flip by hand, the way `CURRENT_ACCOUNT` does on the dashboard.
 * Delete the constant once the extractor feeds these screens for real.
 */
export type PreviewScreen =
  | 'reading'
  | 'order'
  | 'reason'
  | 'policy'
  | 'method'
  | 'review'
  | 'standing-access'

export const PREVIEW: PreviewScreen | null = null
