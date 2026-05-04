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
  email:    { check: v => EMAIL.test(v),                          message: 'Невірний формат email' },
  phone:    { check: v => PHONE.test(v),                          message: 'Невірний формат телефону' },
  url:      { check: v => URL.test(v),                            message: 'Невірний формат URL' },
  iban_ua:  { check: v => IBAN_UA.test(v.replace(/\s/g, '').toUpperCase()), message: 'Невірний IBAN (очікується UA + 27 цифр)' },
  iban:     { check: v => IBAN.test(v.replace(/\s/g, '').toUpperCase()),    message: 'Невірний формат IBAN' },
  edrpou:   { check: v => EDRPOU.test(v.trim()),                  message: 'Невірний код ЄДРПОУ (8 або 10 цифр)' },
  rnocpp:   { check: v => RNOCPP.test(v.trim()),                  message: 'Невірний РНОКПП (10 цифр)' },
}

export function validateFieldValue(validatorName: string, value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null
  const def = VALIDATORS[validatorName]
  if (!def) return null
  return def.check(String(value)) ? null : def.message
}
