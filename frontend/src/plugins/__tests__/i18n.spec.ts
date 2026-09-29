import { beforeEach, describe, expect, it } from 'vitest'
import { i18n, tn } from '../i18n'

const t = i18n.global.t

describe('i18n', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'uk'
    i18n.global.setLocaleMessage('uk', {
      'Hello {name}': 'Привіт, {name}',
      '{n} file\u00000': '{n} файл',
      '{n} file\u00002': '{n} файлів',
    })
  })

  it('interpolates translated messages', () => {
    expect(t('Hello {name}', { name: 'Оля' })).toBe('Привіт, Оля')
  })

  it('interpolates untranslated keys too', () => {
    expect(t('Saved {time}', { time: '5 min ago' })).toBe('Saved 5 min ago')
  })

  it('strips the context prefix of an untranslated key', () => {
    expect(t('button|Save')).toBe('Save')
  })

  it('keeps a bare @ in an untranslated key', () => {
    expect(t('Write a comment... @ to mention')).toBe('Write a comment... @ to mention')
  })

  it('tn uses the translated form, falling back to English', () => {
    expect(tn('{n} file', '{n} files', 5)).toBe('5 файлів')
    expect(tn('{n} file', '{n} files', 3)).toBe('3 files')
    expect(tn('{n} file', '{n} files', 1)).toBe('1 файл')
  })
})
