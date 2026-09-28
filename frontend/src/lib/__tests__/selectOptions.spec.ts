import { describe, expect, it } from 'vitest'
import { parseSelectOptions, selectOptionLabel } from '@/lib/selectOptions'

describe('selectOptions', () => {
  it('keeps values and falls back to the value as label', () => {
    expect(parseSelectOptions('Open\nlist|LayoutList')).toEqual([
      { value: 'Open', label: 'Open', icon: null },
      { value: 'list', label: 'list', icon: 'LayoutList' },
    ])
  })

  it('uses translated captions without touching values', () => {
    const opts = parseSelectOptions('Open\nClosed', { Open: 'Відкрито' })
    expect(opts.map((o) => [o.value, o.label])).toEqual([['Open', 'Відкрито'], ['Closed', 'Closed']])
  })

  it('selectOptionLabel resolves one stored value', () => {
    expect(selectOptionLabel({ option_labels: { High: 'Високий' } }, 'High')).toBe('Високий')
    expect(selectOptionLabel({}, 'Low')).toBe('Low')
    expect(selectOptionLabel(undefined, null)).toBe('')
  })
})
