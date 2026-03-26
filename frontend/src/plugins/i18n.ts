/**
 * Vue i18n plugin — loads translations from PO-based backend API.
 *
 * Source of truth: PO/POT files on the backend.
 * Frontend receives a JSON bundle via GET /api/v1/translations/{locale}.
 * Fallback: bundled uk.json / en.json for offline dev.
 *
 * Default language: Ukrainian (uk).
 *
 * Usage in components:
 *   import { useI18n } from 'vue-i18n'
 *   const { t } = useI18n()
 *   t('Document not found')  // "Документ не знайдено"
 *   t('button|Save')         // "Зберегти" (with context)
 */

import { createI18n } from 'vue-i18n'

// Bundled fallback translations (subset for offline dev)
import ukFallback from '@/locales/uk.json'
import enFallback from '@/locales/en.json'

export type SupportedLocale = 'uk' | 'en'

const STORAGE_KEY = 'grunt-locale'

function getSavedLocale(): SupportedLocale {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'uk' || saved === 'en') return saved
  return 'uk'
}

export const i18n = createI18n({
  legacy: false,
  locale: getSavedLocale(),
  fallbackLocale: 'en',
  messages: {
    uk: ukFallback,
    en: enFallback,
  },
  missingWarn: false,
  fallbackWarn: false,
})

/**
 * Load translations from the backend API and merge into vue-i18n.
 * Call this after the API client is initialized (e.g., in App.vue onMounted).
 */
export async function loadRemoteTranslations(locale?: SupportedLocale): Promise<void> {
  const lang = locale || getSavedLocale()
  try {
    const response = await fetch(`/api/v1/translations/${lang}`)
    if (response.ok) {
      const data = await response.json()
      if (data.success && data.data) {
        i18n.global.mergeLocaleMessage(lang, data.data)
      }
    }
  } catch {
    // Fallback to bundled translations — already loaded
  }
}

export function setLocale(locale: SupportedLocale): void {
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.setAttribute('lang', locale)
  // Optionally load remote translations for the new locale
  loadRemoteTranslations(locale)
}

export default i18n
