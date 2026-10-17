import { describe, it, expect } from 'vitest'
import { durationUnit, formatDuration, splitDuration } from '@/core/duration'

// i18n has no catalog loaded in tests - keys come back as English source.
describe('formatDuration', () => {
  it('is empty for no value', () => {
    expect(formatDuration(null)).toBe('')
    expect(formatDuration(undefined)).toBe('')
    expect(formatDuration('')).toBe('')
  })

  it('breaks seconds into units', () => {
    expect(formatDuration(0)).toBe('0 s')
    expect(formatDuration(45)).toBe('45 s')
    expect(formatDuration(9000)).toBe('2 h 30 min')
    expect(formatDuration(90061)).toBe('1 d 1 h 1 min 1 s')
  })

  it('reads milliseconds', () => {
    expect(formatDuration(450, 'ms')).toBe('450 ms')
    expect(formatDuration(0, 'ms')).toBe('0 ms')
    expect(formatDuration(61_500, 'ms')).toBe('1 min 2 s')
    expect(formatDuration(3_600_000, 'ms')).toBe('1 h')
  })

  it('keeps maxParts consecutive units from the largest', () => {
    expect(formatDuration(90061, 's', 2)).toBe('1 d 1 h')
    expect(formatDuration(86_700, 's', 2)).toBe('1 d') // 1 d 0 h 5 min
  })

  it('signs negatives and passes junk through', () => {
    expect(formatDuration(-90)).toBe('−1 min 30 s')
    expect(formatDuration('abc')).toBe('abc')
  })
})

describe('durationUnit', () => {
  it('defaults to seconds', () => {
    expect(durationUnit({ options: undefined })).toBe('s')
    expect(durationUnit({ options: '' })).toBe('s')
    expect(durationUnit({ options: ' MS ' })).toBe('ms')
  })
})

describe('splitDuration', () => {
  const counts = (total: number, unit?: 's' | 'ms') =>
    Object.fromEntries(splitDuration(total, unit).map((s) => [s.key, s.count]))

  it('splits seconds into d/h/min/s', () => {
    expect(counts(90061)).toEqual({ d: 1, h: 1, min: 1, s: 1 })
    expect(counts(0)).toEqual({ d: 0, h: 0, min: 0, s: 0 })
  })

  it('adds an ms segment for milliseconds', () => {
    expect(counts(715_667, 'ms')).toEqual({ d: 0, h: 0, min: 11, s: 55, ms: 667 })
  })

  it('sizes steps in the stored unit', () => {
    expect(splitDuration(0).map((s) => s.size)).toEqual([86400, 3600, 60, 1])
    expect(splitDuration(0, 'ms').map((s) => s.size)).toEqual([86_400_000, 3_600_000, 60_000, 1000, 1])
  })
})
