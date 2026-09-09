import { describe, it, expect } from 'vitest'
import { tryCalc, formatCalcResult } from '@/lib/calc'

describe('tryCalc', () => {
    it('respects operator precedence', () => {
        expect(tryCalc('2+2*2')).toBe(6)
        expect(tryCalc('(2+2)*2')).toBe(8)
        expect(tryCalc('10 - 2 - 3')).toBe(5)
    })

    it('handles division, modulo and decimals', () => {
        expect(tryCalc('7/2')).toBe(3.5)
        expect(tryCalc('10 % 3')).toBe(1)
        expect(tryCalc('.5 + .25')).toBe(0.75)
    })

    it('handles unary minus and power', () => {
        expect(tryCalc('-3 + 5')).toBe(2)
        expect(tryCalc('2^10')).toBe(1024)
        expect(tryCalc('2**3**2')).toBe(512) // right-associative
        expect(tryCalc('-2^2')).toBe(-4) // unary binds looser than ^
    })

    it('returns null for non-expressions and incomplete input', () => {
        expect(tryCalc('')).toBeNull()
        expect(tryCalc('42')).toBeNull()
        expect(tryCalc('2024')).toBeNull()
        expect(tryCalc('2 +')).toBeNull()
        expect(tryCalc('User')).toBeNull()
        expect(tryCalc('2 + abc')).toBeNull()
        expect(tryCalc('1..2 + 1')).toBeNull()
        expect(tryCalc('(1+2')).toBeNull()
    })

    it('returns null for non-finite results', () => {
        expect(tryCalc('1/0')).toBeNull()
        expect(tryCalc('0/0')).toBeNull()
    })
})

describe('formatCalcResult', () => {
    it('keeps integers plain', () => {
        expect(formatCalcResult(6)).toBe('6')
        expect(formatCalcResult(-0)).toBe('0')
    })

    it('trims floating-point noise', () => {
        expect(formatCalcResult(0.1 + 0.2)).toBe('0.3')
        expect(formatCalcResult(10 / 3)).toBe('3.333333333')
    })
})
