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

describe('useFormValidation - mandatory_depends_on', () => {
  function check(form: Record<string, unknown>) {
    const v = useFormValidation({
      doctype: 'Payment',
      dt: ref(
        doctype('Payment', [
          field({ fieldname: 'method', fieldtype: 'Data', label: 'Method' }),
          field({
            fieldname: 'iban',
            fieldtype: 'Data',
            label: 'IBAN',
            mandatory_depends_on: "eval:doc.method == 'Bank'",
          }),
          field({
            fieldname: 'note',
            fieldtype: 'Data',
            label: 'Note',
            depends_on: "eval:doc.method == 'Other'",
            mandatory_depends_on: 'eval:true',
          }),
        ]),
      ),
      form: ref(form),
      displayOverrides: {},
      reqdOverrides: {},
      toast: { error: vi.fn() },
    })
    return { ok: v.validateForm(), errors: v.validationErrors.value }
  }

  beforeEach(() => setActivePinia(createPinia()))

  it('requires the field while its condition holds', () => {
    const bank = check({ method: 'Bank', iban: '' })
    expect(bank.ok).toBe(false)
    expect(bank.errors.iban).toBeTruthy()
    expect(check({ method: 'Bank', iban: 'UA12' }).ok).toBe(true)
    expect(check({ method: 'Cash', iban: '' }).ok).toBe(true)
  })

  it('does not require a field its depends_on hides', () => {
    expect(check({ method: 'Cash', note: '' }).errors.note).toBeUndefined()
    expect(check({ method: 'Other', note: '' }).errors.note).toBeTruthy()
  })
})
