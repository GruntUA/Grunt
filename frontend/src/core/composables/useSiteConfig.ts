/**
 * Site-wide configuration sourced from the `SystemSettings` singleton, plus the
 * signed-in user's own `language` / `timezone` overrides.
 *
 * Precedence for the *effective* locale & timezone:
 *   1. the logged-in user's `User.language` / `User.timezone`   (applyUserPrefs)
 *   2. the visitor's explicit browser choice - localStorage['grunt-locale']
 *   3. `SystemSettings` defaults                                (loadSiteConfig)
 *
 * Singleton state (same pattern as `useColorMode`) so plain modules - e.g.
 * `core/datetime.ts` - can read it without a component instance.
 */

import { reactive, toRefs } from 'vue'
import i18n, { setLocale, type SupportedLocale } from '@/plugins/i18n'

const LOCALE_STORAGE_KEY = 'grunt-locale'

export interface UiLanguage {
  /** Short code, e.g. "uk". */
  code: string
  /** Native name, e.g. "Українська". */
  name: string
}

export interface SiteConfig {
  appName: string
  appLogo: string
  /** Site default UI language (short code, e.g. "uk"). */
  language: string
  /** UI languages the switcher offers - every locale with a translation catalog. */
  languages: UiLanguage[]
  /** Effective IANA tz name, e.g. "Europe/Kyiv". Empty = use the browser's zone. */
  timezone: string
  /** "dd.mm.yyyy" | "dd/mm/yyyy" | "yyyy-mm-dd" */
  dateFormat: string
  allowRegistration: boolean
  loaded: boolean
}

const state = reactive<SiteConfig>({
  appName: 'Ґрунт',
  appLogo: '',
  language: 'uk',
  languages: [
    { code: 'en', name: 'English' },
    { code: 'uk', name: 'Українська' },
  ],
  timezone: '',
  dateFormat: 'dd.mm.yyyy',
  allowRegistration: false,
  loaded: false,
})

// Site default vs. per-user override - `state.timezone` is whichever applies.
let _siteTimezone = ''
let _userTimezone: string | null = null

let _promise: Promise<void> | null = null

function toShortLocale(tag: string): SupportedLocale {
  return tag.slice(0, 2).toLowerCase()
}

function _syncTimezone(): void {
  state.timezone = _userTimezone || _siteTimezone
}

async function _load(): Promise<void> {
  try {
    const res = await fetch('/api/v1/method/grunt.api.v1.site_config.get_public_config')
    if (res.ok) {
      const body = await res.json()
      const data = body?.data ?? body
      if (data && typeof data === 'object') {
        state.appName = data.app_name || state.appName
        state.appLogo = data.app_logo || ''
        state.language = data.language ? toShortLocale(data.language) : state.language
        if (Array.isArray(data.languages) && data.languages.length) state.languages = data.languages
        _siteTimezone = data.timezone || ''
        state.dateFormat = data.date_format || state.dateFormat
        state.allowRegistration = !!data.allow_user_registration
      }
    }
  } catch {
    // Offline / not configured - keep the defaults.
  } finally {
    state.loaded = true
    _syncTimezone()
  }

  // Seed the UI locale from the backend only when the visitor has not made
  // their own choice (that choice lives in localStorage['grunt-locale']).
  try {
    if (!localStorage.getItem(LOCALE_STORAGE_KEY)) {
      if (i18n.global.locale.value !== state.language) setLocale(state.language)
      else document.documentElement.setAttribute('lang', state.language)
    }
  } catch {
    // localStorage unavailable - ignore.
  }
}

/** Idempotent: returns the in-flight/settled load promise. */
export function loadSiteConfig(): Promise<void> {
  if (!_promise) _promise = _load()
  return _promise
}

/** Force a fresh fetch - e.g. right after the setup wizard saves settings. */
export function reloadSiteConfig(): Promise<void> {
  _promise = _load()
  return _promise
}

/**
 * Apply the signed-in user's own preferences over the site defaults. Call with
 * `{}` on logout to fall back to the site config.
 */
export function applyUserPrefs(prefs: { language?: string | null; timezone?: string | null } = {}): void {
  _userTimezone = prefs.timezone?.trim() || null
  _syncTimezone()

  if (prefs.language) {
    const short = toShortLocale(prefs.language)
    if (i18n.global.locale.value !== short) setLocale(short)
  }
}

/** Reactive refs for use inside components. */
export function useSiteConfig() {
  return { ...toRefs(state), loadSiteConfig }
}

/** Raw state for non-component modules (e.g. `core/datetime.ts`). */
export function siteConfigState(): SiteConfig {
  return state
}
