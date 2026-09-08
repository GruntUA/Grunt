/**
 * Browser-tab title.
 *
 * `document.title` is built as `"<page> · <appName>"`, falling back to just the
 * app name when a route/page has no descriptive part. The router sets a
 * param-derived default on every navigation (see `router/index.ts`); pages that
 * load richer data (a document's title, a DocType label, a Page/Report name)
 * refine it by calling `setPageTitle()` once that data is in.
 */

import { siteConfigState } from './useSiteConfig'

let currentPart = ''

function render(): void {
  const app = siteConfigState().appName || 'Ґрунт'
  document.title = currentPart ? `${currentPart} · ${app}` : app
}

/** Set the descriptive part of the tab title. Empty/nullish → just the app name. */
export function setPageTitle(part?: string | null): void {
  currentPart = (part ?? '').trim()
  render()
}

/** Re-render with the current part — e.g. after the app name loads async. */
export function refreshPageTitle(): void {
  render()
}
