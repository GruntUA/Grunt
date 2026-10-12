import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import type { DocField, DocType } from '@/types'
import { useDocTypeStore } from '@/stores/doctype'
import { useFormValidation } from '../useFormValidation'

const field = (f: Partial<DocField>) => f as DocField
const doctype = (name: string, fields: DocField[]) => ({ name, fields }) as unknown as DocType

function setup(rows: Record<string, unknown>[]) {
  const toast = { error: vi.fn() }
  const parent = doctype('Order', [
    field({ fieldname: 'title', fieldtype: 'Data', label: 'Title' }),
    field({ fieldname: 'items', fieldtype: 'Table', label: 'Items', options: 'OrderItem' }),
  ])
  const v = useFormValidation({
    doctype: 'Order',
    dt: ref(parent),
    form: ref({ title: 'x', items: rows }),
    displayOverrides: {},
    reqdOverrides: {},
    toast,
  })
  return { v, toast }
}

describe('useFormValidation - child table rows', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useDocTypeStore().cache.set(
      'OrderItem',
      doctype('OrderItem', [
        field({ fieldname: 'item', fieldtype: 'Data', label: 'Item', required: true }),
        field({ fieldname: 'qty', fieldtype: 'Int', label: 'Qty', min_value: 1 }),
      ]),
    )
  })

  it('blocks Save on an invalid row and points at the table field', () => {
    const { v, toast } = setup([{ item: 'a', qty: 2 }, { item: 'b', qty: 0 }])
    expect(v.validateForm()).toBe(false)
    expect(v.validationErrors.value.items).toContain('2')
    expect(toast.error).toHaveBeenCalledOnce()
  })

  it('reports an empty required cell', () => {
    const { v } = setup([{ item: '', qty: 1 }])
    expect(v.validateForm()).toBe(false)
    expect(v.validationErrors.value.items).toBeTruthy()
  })

  it('passes valid rows, and tables whose schema is not loaded', () => {
    expect(setup([{ item: 'a', qty: 1 }]).v.validateForm()).toBe(true)
    useDocTypeStore().cache.clear()
    expect(setup([{ item: '', qty: 0 }]).v.validateForm()).toBe(true)
  })
})
