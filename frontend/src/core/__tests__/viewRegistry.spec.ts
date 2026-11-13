import { describe, expect, it } from 'vitest'

import { getAvailableViewTypes, getViewDef, isViewAvailable } from '@/core/viewRegistry'
import type { DocType } from '@/types'

const dt = (name: string, fields: Partial<DocType['fields'][number]>[] = []) =>
  ({ name, fields }) as unknown as DocType

describe('isViewAvailable', () => {
  it('offers the permission matrix only on the DocType list', () => {
    const matrix = getViewDef('permissions')!
    expect(isViewAvailable(matrix, dt('DocType'))).toBe(true)
    expect(isViewAvailable(matrix, dt('Invoice'))).toBe(false)
    expect(isViewAvailable(matrix, null)).toBe(false)
    expect(getAvailableViewTypes(dt('Invoice'))).not.toContain('permissions')
    expect(getAvailableViewTypes(dt('DocType'))).toContain('permissions')
  })

  it('keeps views without a check available everywhere', () => {
    expect(isViewAvailable(getViewDef('list')!, null)).toBe(true)
    expect(getAvailableViewTypes(dt('Invoice'))).toContain('list')
  })
})
