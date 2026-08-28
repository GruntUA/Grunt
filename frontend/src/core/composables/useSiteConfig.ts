/**
 * Site-wide configuration sourced from the `SystemSettings` singleton.
 *
 * Singleton state (same pattern as `useColorMode`) so plain modules — e.g.
 * `core/datetime.ts` — can read it without a component instance.
 *
 * Loaded once on boot: `main.ts` fires `loadSiteConfig()`, the router guard
 * awaits the same promise before resolving the first route.
 */

import { reactive, toRefs } from 'vue'
import { setLocale, type SupportedLocale } from '@/plugins/i18n'

const LOCALE_STORAGE_KEY = 'grunt-locale'

export interface SiteConfig {
  appName: string
  appLogo: string
  /** Backend locale tag, e.g. "uk-UA" / "en-US". */
  language: string
  /** IANA tz name, e.g. "Europe/Kyiv". Empty = use the browser's zone. */
  timezone: string
  /** "dd.mm.yyyy" | "dd/mm/yyyy" | "yyyy-mm-dd" */
  dateFormat: string
  allowRegistration: boolean
  loaded: boolean
}

const state = reactive<SiteConfig>({
  appName: 'Ґрунт',
  appLogo: '',
  language: 'uk-UA',
  timezone: '',
  dateFormat: 'dd.mm.yyyy',
  allowRegistration: false,
  loaded: false,
})

let _promise: Promise<void> | null = null

function toShortLocale(tag: string): SupportedLocale {
  return tag.toLowerCase().startsWith('en') ? 'en' : 'uk'
}

async function _load(): Promise<void> {
  try {
    const res = await fetch(
      '/api/v1/method/grunt.api.v1.site_config.get_public_config',
    )
    if (res.ok) {
      const body = await res.json()
      const data = body?.data ?? body
      if (data && typeof data === 'object') {
        state.appName = data.app_name || state.appName
        state.appLogo = data.app_logo || ''
        state.language = data.language || state.language
        state.timezone = data.timezone || ''
        state.dateFormat = data.date_format || state.dateFormat
        state.allowRegistration = !!data.allow_user_registration
      }
    }
  } catch {
    // Offline / not configured — keep the defaults.
  } finally {
    state.loaded = true
  }

  // Seed the UI locale from the backend only when the visitor has not made
  // their own choice (that choice lives in localStorage['grunt-locale']).
  try {
    if (!localStorage.getItem(LOCALE_STORAGE_KEY)) {
      const short = toShortLocale(state.language)
      if (short !== 'uk') setLocale(short)
      else document.documentElement.setAttribute('lang', 'uk')
    }
  } catch {
    // localStorage unavailable — ignore.
  }
}

/** Idempotent: returns the in-flight/settled load promise. */
export function loadSiteConfig(): Promise<void> {
  if (!_promise) _promise = _load()
  return _promise
}

/** Force a fresh fetch — e.g. right after the setup wizard saves settings. */
export function reloadSiteConfig(): Promise<void> {
  _promise = _load()
  return _promise
}

/** Reactive refs for use inside components. */
export function useSiteConfig() {
  return { ...toRefs(state), loadSiteConfig }
}

/** Raw state for non-component modules (e.g. `core/datetime.ts`). */
export function siteConfigState(): SiteConfig {
  return state
}
