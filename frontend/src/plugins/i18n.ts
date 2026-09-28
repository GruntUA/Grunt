/**
 * Vue i18n plugin — loads translations from PO-based backend API.
 *
 * Source of truth: PO/POT files on the backend.
 * Frontend receives a JSON bundle via GET /api/v1/translations/{locale}.
 * English source strings are used as keys — vue-i18n returns the key itself
 * when no translation is found, so English always works without a translation file.
 *
 * UI languages are dynamic: every locale with a backend translation catalog
 * (see `get_public_config().languages`). Until the site config arrives the
 * visitor's saved choice — or `uk` — is used.
 *
 * Usage in components:
 *   import { useI18n } from 'vue-i18n'
 *   const { t } = useI18n()
 *   t('Document not found')  // → "Документ не знайдено"
 *   t('button|Save')         // → "Зберегти" (with context)
 *
 *   import { tn } from '@/plugins/i18n'
 *   tn('{n} file', '{n} files', count)  // plural-aware; mirrors backend ngettext
 */

import { createI18n } from 'vue-i18n'

/** A short UI language code (`uk`, `en`, `pl`, …). */
export type SupportedLocale = string

const STORAGE_KEY = 'grunt-locale'
const VERSION_KEY = 'grunt-locale-version'

function getSavedLocale(): SupportedLocale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && /^[a-z]{2}$/.test(saved)) return saved
  } catch {
    // storage unavailable
  }
  return 'uk'
}

export const i18n = createI18n({
  legacy: false,
  locale: getSavedLocale(),
  fallbackLocale: 'en',
  messages: {},
  missingWarn: false,
  fallbackWarn: false,
})

/**
 * PO strings are plain text, but vue-i18n compiles them: a bare `@` starts a
 * linked message (`@:key`) and fails with "Invalid linked format". Escape it
 * as a literal; `{…}` placeholders stay intact for interpolation.
 */
function escapeMessages(messages: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(messages)) {
    out[k] = typeof v === 'string' ? v.replace(/@/g, "{'@'}") : v
  }
  return out
}

/**
 * Load translations from the backend API and merge into vue-i18n.
 * Called from App.vue onMounted after the API client is ready.
 */
export async function loadRemoteTranslations(locale?: SupportedLocale): Promise<void> {
  const lang = locale || getSavedLocale()
  try {
    const response = await fetch(`/api/v1/method/grunt.api.v1.translations.get_translations?locale=${lang}`)
    if (response.ok) {
      const data = await response.json()
      const bundle = data.success ? data.data : null
      if (bundle && bundle.messages) {
        const key = `${VERSION_KEY}:${lang}`
        const seen = localStorage.getItem(key)
        if (seen && seen === bundle.version && Object.keys(i18n.global.getLocaleMessage(lang)).length) {
          return
        }
        i18n.global.mergeLocaleMessage(lang, escapeMessages(bundle.messages))
        try {
          localStorage.setItem(key, bundle.version ?? '')
        } catch {
          // storage unavailable — re-merge next time, harmless
        }
      }
    }
  } catch {
    // No translations available — English source strings shown as-is
  }
}

// ── Plural forms ────────────────────────────────────────────────────────────
// Kept in step with grunt/i18n/plurals.py.
function slavic3(n: number): number {
  n = Math.abs(n)
  if (n % 10 === 1 && n % 100 !== 11) return 0
  if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return 1
  return 2
}
const PLURAL_RULES: Record<string, (n: number) => number> = {
  en: (n) => (Math.abs(n) === 1 ? 0 : 1),
  uk: slavic3, ru: slavic3, pl: slavic3, cs: slavic3, sk: slavic3,
}

function pluralIndex(locale: string, n: number): number {
  return (PLURAL_RULES[locale] ?? PLURAL_RULES.en)(n)
}

/**
 * Mark a key for the i18n extractor without translating it (gettext_noop).
 * For module-level constants that are translated where rendered: `t(CONST)`.
 */
export const N_ = (key: string): string => key

/**
 * Plural-aware translate — mirrors the backend `ngettext`.
 *
 * Looks up `<singular>\u0000<form-index>` in the bundle (the form index comes
 * from the current locale's plural rule); falls back to the English
 * singular / plural. `{n}` and `{count}` are interpolated with `n`.
 */
export function tn(singular: string, plural: string, n: number, ctx?: string): string {
  const locale = i18n.global.locale.value
  const base = ctx ? `${ctx}|${singular}` : singular
  const key = `${base}\u0000${pluralIndex(locale, n)}`
  let out = i18n.global.t(key)
  if (out === key) out = Math.abs(n) === 1 ? singular : plural
  return out.replace(/\{n\}|\{count\}/g, String(n))
}

export function setLocale(locale: SupportedLocale): void {
  i18n.global.locale.value = locale
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    // storage unavailable — the choice lasts for this page only
  }
  document.documentElement.setAttribute('lang', locale)
  loadRemoteTranslations(locale)
  // DocType schemas are translated server-side per request language — drop the
  // cache so the next render refetches labels in the new language.
  import('@/stores/doctype')
    .then(({ useDocTypeStore }) => useDocTypeStore().invalidateAll())
    .catch(() => {})
}

export default i18n
