/**
 * Vue i18n plugin — loads translations from PO-based backend API.
 *
 * Source of truth: PO/POT files on the backend.
 * Frontend receives a JSON bundle via GET /api/v1/translations/{locale}.
 * English source strings are used as keys — vue-i18n returns the key itself
 * when no translation is found, so English always works without a translation file.
 *
 * Default language: Ukrainian (uk).
 *
 * Usage in components:
 *   import { useI18n } from 'vue-i18n'
 *   const { t } = useI18n()
 *   t('Document not found')  // → "Документ не знайдено"
 *   t('button|Save')         // → "Зберегти" (with context)
 */

import { createI18n } from 'vue-i18n'

export type SupportedLocale = 'uk' | 'en'

const STORAGE_KEY = 'grunt-locale'
const VERSION_KEY = 'grunt-locale-version'

function getSavedLocale(): SupportedLocale {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'uk' || saved === 'en') return saved
  return 'uk'
}

export const i18n = createI18n({
  legacy: false,
  locale: getSavedLocale(),
  fallbackLocale: 'en',
  messages: { uk: {}, en: {} },
  missingWarn: false,
  fallbackWarn: false,
})

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
        i18n.global.mergeLocaleMessage(lang, bundle.messages)
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

export function setLocale(locale: SupportedLocale): void {
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.setAttribute('lang', locale)
  loadRemoteTranslations(locale)
}

export default i18n
