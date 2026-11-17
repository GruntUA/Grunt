import { describe, expect, it } from 'vitest'
import { formatCondition, parseCondition } from '../condition'

describe('row condition', () => {
  it('parses what the server accepts', () => {
    expect(parseCondition('owner == user')).toEqual({ field: 'owner', sub: '', op: '==', kind: 'user', value: '' })
    expect(parseCondition("status != 'Closed'")).toEqual({ field: 'status', sub: '', op: '!=', kind: 'value', value: 'Closed' })
    expect(parseCondition('team.lead == user')).toMatchObject({ field: 'team', sub: 'lead', kind: 'user' })
    expect(parseCondition('title == "It\'s"')).toMatchObject({ kind: 'value', value: "It's" })
  })

  it('rejects anything else', () => {
    for (const text of ['', 'owner', 'owner == 5', "a == 'x' and b == 'y'", 'a.b.c == user']) {
      expect(parseCondition(text)).toBeNull()
    }
  })

  it('round-trips', () => {
    for (const text of ['owner == user', "status != 'Closed'", 'team.lead == user', 'title == "It\'s"']) {
      expect(formatCondition(parseCondition(text)!)).toBe(text)
    }
    expect(formatCondition({ field: '', sub: '', op: '==', kind: 'user', value: '' })).toBe('')
  })

  it('never alters a value it cannot hold', () => {
    const both = { field: 'title', sub: '', op: '==' as const, kind: 'value' as const, value: `Bob's "Draft"` }
    expect(formatCondition(both)).toBeNull()
  })
})
