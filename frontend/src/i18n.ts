import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import uk from './locales/uk.json'

export type Locale = 'en' | 'uk'

const savedLocale = (localStorage.getItem('grunt_locale') as Locale | null) ?? 'en'

const i18n = createI18n({
  legacy: false,
  locale: savedLocale,
  fallbackLocale: 'en',
  messages: { en, uk },
})

export function setLocale(locale: Locale) {
  ;(i18n.global.locale as any).value = locale
  localStorage.setItem('grunt_locale', locale)
  document.documentElement.lang = locale
}

export { i18n }
export default i18n
