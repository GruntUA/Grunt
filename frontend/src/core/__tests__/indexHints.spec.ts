import { describe, it, expect } from 'vitest'
import { computeIndexHints } from '@/core/indexHints'
import type { DocType } from '@/types'

function dt(partial: Partial<DocType>): DocType {
  return { name: 'Test', label: 'Test', module: 'test', fields: [], ...partial }
}

describe('computeIndexHints', () => {
  it('flags a known polymorphic pair missing from doctype.indexes', () => {
    const hints = computeIndexHints(dt({
      fields: [
        { fieldname: 'reference_doctype', label: 'Ref type', fieldtype: 'Link' },
        { fieldname: 'reference_id', label: 'Ref id', fieldtype: 'Text' },
      ],
    }))
    expect(hints).toHaveLength(1)
    expect(hints[0].field).toBe('reference_doctype+reference_id')
  })

  it('does not flag a polymorphic pair already covered by doctype.indexes', () => {
    const hints = computeIndexHints(dt({
      fields: [
        { fieldname: 'reference_doctype', label: 'Ref type', fieldtype: 'Link' },
        { fieldname: 'reference_id', label: 'Ref id', fieldtype: 'Text' },
      ],
      indexes: [['reference_doctype', 'reference_id']],
    }))
    expect(hints).toHaveLength(0)
  })

  it('does not flag a pair when only one of the two fields is present', () => {
    const hints = computeIndexHints(dt({
      fields: [{ fieldname: 'reference_doctype', label: 'Ref type', fieldtype: 'Link' }],
    }))
    expect(hints).toHaveLength(0)
  })

  it('flags each known pair independently (source/target/parent conventions)', () => {
    const hints = computeIndexHints(dt({
      fields: [
        { fieldname: 'source_doctype', label: 'Src type', fieldtype: 'Link' },
        { fieldname: 'source_id', label: 'Src id', fieldtype: 'Text' },
        { fieldname: 'target_doctype', label: 'Tgt type', fieldtype: 'Link' },
        { fieldname: 'target_id', label: 'Tgt id', fieldtype: 'Text' },
      ],
    }))
    expect(hints.map((h) => h.field).sort()).toEqual([
      'source_doctype+source_id',
      'target_doctype+target_id',
    ])
  })

  it('does not flag a doctype with no polymorphic pairs at all', () => {
    const hints = computeIndexHints(dt({
      fields: [
        { fieldname: 'title', label: 'Title', fieldtype: 'Text', in_filter: true },
        { fieldname: 'owner_link', label: 'Owner', fieldtype: 'Link', in_filter: true },
      ],
    }))
    expect(hints).toHaveLength(0)
  })

  it('returns no hints for a virtual doctype, even with an unindexed pair', () => {
    const hints = computeIndexHints(dt({
      is_virtual: true,
      fields: [
        { fieldname: 'reference_doctype', label: 'Ref type', fieldtype: 'Link' },
        { fieldname: 'reference_id', label: 'Ref id', fieldtype: 'Text' },
      ],
    }))
    expect(hints).toHaveLength(0)
  })

  it('returns no hints for a null doctype', () => {
    expect(computeIndexHints(null)).toEqual([])
  })
})
