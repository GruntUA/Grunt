import { describe, expect, it } from 'vitest'
import { addUrlFilters, periodRange } from '../drilldown'

describe('report drill-down', () => {
  it('turns a date-group label into a [from, to) range', () => {
    expect(periodRange('day', '2026-02-28')).toEqual(['2026-02-28', '2026-03-01'])
    expect(periodRange('month', '2026-12')).toEqual(['2026-12-01', '2027-01-01'])
    expect(periodRange('quarter', '2026-Q3')).toEqual(['2026-07-01', '2026-10-01'])
    expect(periodRange('year', '2026')).toEqual(['2026-01-01', '2027-01-01'])
    expect(periodRange('month', 'garbage')).toBeNull()
  })

  it('maps report filters to list URL filters, skipping what the URL cannot express', () => {
    const q: Record<string, string> = {}
    addUrlFilters(q, { status: 'Open', amount__gte: 5, name__ilike: 'ab', x__isnull: true, y__eq: ['A'] })
    expect(q).toEqual({
      'filter[status__eq]': 'Open',
      'filter[amount__gte]': '5',
      'filter[name__ilike]': 'ab',
    })
  })

  it('passes in / nin lists as CSV', () => {
    const q: Record<string, string> = {}
    addUrlFilters(q, { region__in: ['A', 'B'], status__nin: 'X,Y' })
    expect(q).toEqual({ 'filter[region__in]': 'A,B', 'filter[status__nin]': 'X,Y' })
  })
})
