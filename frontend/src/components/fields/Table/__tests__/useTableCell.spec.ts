import { describe, expect, it } from 'vitest'
import type { DocField } from '@/types'
import { useTableCell } from '../useTableCell'

const actions = {
  fieldname: 'actions',
  fieldtype: 'MultiSelect',
  label: 'Actions',
  options: 'read\nwrite',
  option_labels: { read: 'Read', write: 'Edit' },
} as unknown as DocField

const display = (row: Record<string, unknown>, f: DocField) => useTableCell().cellDisplay(row, f)

describe('table cell text', () => {
  it('a MultiSelect shows its option labels, not the raw list', () => {
    expect(display({ actions: ['read', 'write'] }, actions)).toBe('Read, Edit')
    expect(display({ actions: '["read"]' }, actions)).toBe('Read')
  })
})
