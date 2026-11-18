import { afterEach, describe, expect, it } from 'vitest'
import { roundNumber, roundToPrecision } from '../numbers'
import { siteConfigState } from '@/core/composables/useSiteConfig'

// The same cases as tests/test_number_precision.py - the form and the server agree.
describe('roundNumber', () => {
  it.each([
    [1.005, 2, 'Half up', 1.01], // Math.round(1.005 * 100) / 100 gives 1
    [2.675, 2, 'Half up', 2.68],
    [0.125, 2, 'Half up', 0.13],
    [0.125, 2, 'Half even', 0.12],
    [0.135, 2, 'Half even', 0.14],
    [-0.125, 2, 'Half up', -0.13],
    [12.5, 0, 'Half even', 12],
    [13.5, 0, 'Half even', 14],
    [1.23456, 3, 'Half up', 1.235],
    [1e-7, 2, 'Half up', 0],
    [123456789.125, 2, 'Half up', 123456789.13],
  ] as const)('%s to %s (%s) -> %s', (n, p, method, expected) => {
    expect(roundNumber(n, p, method)).toBe(expected)
  })

  it('gives no negative zero', () => {
    expect(Object.is(roundNumber(-0.001, 2), 0)).toBe(true)
  })
})

describe('roundToPrecision', () => {
  afterEach(() => { siteConfigState().roundingMethod = 'Half up' })

  it('keeps the value without a precision and follows the site method', () => {
    expect(roundToPrecision(1.23456789, undefined)).toBe(1.23456789)
    expect(roundToPrecision(0.125, 2)).toBe(0.13)
    siteConfigState().roundingMethod = 'Half even'
    expect(roundToPrecision(0.125, 2)).toBe(0.12)
  })
})
