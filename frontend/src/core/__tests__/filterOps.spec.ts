import { describe, expect, it } from 'vitest'
import { displayOp, displayOpOrNull, filterKey, filtersToRaw, MULTI_VALUE_OPS, NO_VALUE_OPS, opLabel, splitFilterKey } from '../filterOps'

describe('filterOps', () => {
  it('splits only known suffixes, longest first', () => {
    expect(splitFilterKey('amount__gte')).toEqual(['amount', 'gte'])
    expect(splitFilterKey('due__lte_or_null')).toEqual(['due', 'lte_or_null'])
    expect(splitFilterKey('dept__child_of')).toEqual(['dept', 'child_of'])
    expect(splitFilterKey('foo__bar')).toEqual(['foo__bar', 'eq'])
    expect(splitFilterKey('my__field__in')).toEqual(['my__field', 'in'])
    expect(splitFilterKey('status')).toEqual(['status', 'eq'])
  })

  it('maps display <-> backend operators', () => {
    expect(filterKey('title', 'like')).toBe('title__ilike')
    expect(filterKey('x', 'unknown')).toBe('x__eq')
    expect(displayOp('nin', 'a')).toBe('not in')
    expect(displayOp('is', 'set')).toBe('is set')
    expect(displayOp('is', 'not set')).toBe('is not set')
    expect(displayOpOrNull('like')).toBe('like')
    expect(displayOpOrNull('isnull')).toBeNull()
    expect(displayOp('isnull', '1')).toBe('=')
  })

  it('derives the value-shape sets', () => {
    expect(MULTI_VALUE_OPS).toEqual(['in', 'not in'])
    expect(NO_VALUE_OPS).toEqual({ 'is set': 'set', 'is not set': 'not set' })
  })

  it('labels operators', () => {
    const t = (k: string) => `T:${k}`
    expect(opLabel('>=', t)).toBe('T:Greater than or equal')
    expect(opLabel('>=', t, true)).toBe('≥')
    expect(opLabel('like', t, true)).toBe('T:Contains')
    expect(opLabel('weird', t)).toBe('weird')
  })

  it('builds raw filters', () => {
    expect(filtersToRaw([
      { fieldname: 'a', op: '>', value: '1' },
      { fieldname: 'b', op: 'is not set', value: 'not set' },
    ] as any)).toEqual({ a__gt: '1', b__is: 'not set' })
  })
})
