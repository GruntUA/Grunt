import i18n, { N_ } from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

/**
 * Client-side field validators.
 * Must stay in sync with grunt/document/validators.py.
 */

type ValidatorFn = (value: string) => boolean

interface ValidatorDef {
  check: ValidatorFn
  message: string
}

const EMAIL = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/
const PHONE = /^\+?[\d\s\-()]{7,20}$/
const URL = /^https?:\/\/[^\s/$.?#].[^\s]*/i
const IBAN_UA = /^UA\d{27}$/
const IBAN = /^[A-Z]{2}\d{2}[A-Z0-9]{1,30}$/
const EDRPOU = /^\d{8}(\d{2})?$/
const RNOCPP = /^\d{10}$/

const VALIDATORS: Record<string, ValidatorDef> = {
  email:    { check: v => EMAIL.test(v),                          message: N_('Invalid email format') },
  phone:    { check: v => PHONE.test(v),                          message: N_('Invalid phone format') },
  url:      { check: v => URL.test(v),                            message: N_('Invalid URL format') },
  iban_ua:  { check: v => IBAN_UA.test(v.replace(/\s/g, '').toUpperCase()), message: N_('Invalid IBAN (expected UA + 27 digits)') },
  iban:     { check: v => IBAN.test(v.replace(/\s/g, '').toUpperCase()),    message: N_('Invalid IBAN format') },
  edrpou:   { check: v => EDRPOU.test(v.trim()),                  message: N_('Invalid EDRPOU code (8 or 10 digits)') },
  rnocpp:   { check: v => RNOCPP.test(v.trim()),                  message: N_('Invalid RNOKPP (10 digits)') },
}

export function validateFieldValue(validatorName: string, value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null
  const def = VALIDATORS[validatorName]
  if (!def) return null
  return def.check(String(value)) ? null : t(def.message)
}
