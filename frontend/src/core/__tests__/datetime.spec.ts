import { describe, it, expect, beforeEach } from 'vitest'
import { siteConfigState } from '@/core/composables/useSiteConfig'
import {
  formatDate,
  formatDateTime,
  formatTime,
  dateFormatSpec,
  EMPTY_DATE,
} from '@/core/datetime'

function setConfig(over: Partial<ReturnType<typeof siteConfigState>>) {
  Object.assign(siteConfigState(), over)
}

beforeEach(() => {
  setConfig({ language: 'uk-UA', timezone: 'UTC', dateFormat: 'dd.mm.yyyy' })
})

describe('core/datetime', () => {
  const ISO = '2026-03-07T09:05:00Z'

  it('maps every date_format', () => {
    setConfig({ dateFormat: 'dd.mm.yyyy' })
    expect(formatDate(ISO)).toBe('07.03.2026')

    setConfig({ dateFormat: 'dd/mm/yyyy' })
    expect(formatDate(ISO)).toBe('07/03/2026')

    setConfig({ dateFormat: 'yyyy-mm-dd' })
    expect(formatDate(ISO)).toBe('2026-03-07')
  })

  it('falls back to dd.mm.yyyy for an unknown format', () => {
    setConfig({ dateFormat: 'nonsense' })
    expect(formatDate(ISO)).toBe('07.03.2026')
  })

  it('applies the configured timezone', () => {
    // 23:30 UTC on the 7th is the 8th in Kyiv (UTC+2/+3)
    const lateNight = '2026-03-07T23:30:00Z'
    setConfig({ timezone: 'UTC' })
    expect(formatDate(lateNight)).toBe('07.03.2026')
    setConfig({ timezone: 'Europe/Kyiv' })
    expect(formatDate(lateNight)).toBe('08.03.2026')
  })

  it('formatDateTime appends 24h time', () => {
    setConfig({ dateFormat: 'yyyy-mm-dd', timezone: 'UTC' })
    expect(formatDateTime(ISO)).toBe('2026-03-07 09:05')
  })

  it('formatTime is zero-padded 24h', () => {
    setConfig({ timezone: 'UTC' })
    expect(formatTime(ISO)).toBe('09:05')
  })

  it('returns the em-dash for empty / invalid input', () => {
    expect(formatDate('')).toBe(EMPTY_DATE)
    expect(formatDate(null)).toBe(EMPTY_DATE)
    expect(formatDate('not-a-date')).toBe(EMPTY_DATE)
    expect(formatDateTime(undefined)).toBe(EMPTY_DATE)
  })

  it('accepts "YYYY-MM-DD HH:MM:SS" (space) strings', () => {
    setConfig({ dateFormat: 'dd.mm.yyyy', timezone: 'UTC' })
    expect(formatDate('2026-03-07 09:05:00')).toBe('07.03.2026')
  })

  it('dateFormatSpec describes separator / order / placeholder', () => {
    setConfig({ dateFormat: 'yyyy-mm-dd' })
    expect(dateFormatSpec()).toEqual({ sep: '-', order: ['y', 'm', 'd'], placeholder: 'РРРР-ММ-ДД' })
    setConfig({ dateFormat: 'dd/mm/yyyy' })
    expect(dateFormatSpec()).toEqual({ sep: '/', order: ['d', 'm', 'y'], placeholder: 'ДД/ММ/РРРР' })
  })
})
