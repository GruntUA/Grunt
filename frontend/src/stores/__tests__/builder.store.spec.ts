import { describe, it, expect, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { useBuilderStore } from '@/stores/builder'
import type { DocType } from '@/types'

function seed(fields: DocType['fields']): DocType {
  return { name: 'Order', label: 'Order', module: 'crm', fields }
}

const names = (b: ReturnType<typeof useBuilderStore>) =>
  (b.doctype?.fields ?? []).map((f) => f.fieldname)

beforeEach(() => setActivePinia(createPinia()))

describe('builder store — field CRUD', () => {
  it('addField appends the field and selects it', () => {
    const b = useBuilderStore()
    b.doctype = seed([{ fieldname: 'title', label: 'Title', fieldtype: 'Data' }])

    b.addField('Int')

    expect(names(b)).toEqual(['title', 'int_field'])
    expect(b.selectedFieldName).toBe('int_field')
    expect(b.selectedField?.fieldtype).toBe('Int')
  })

  it('updateField patches props and keeps the selection pinned across a rename', () => {
    const b = useBuilderStore()
    b.doctype = seed([{ fieldname: 'title', label: 'Title', fieldtype: 'Data' }])
    b.selectField('title')

    b.updateField('title', { label: 'Heading' })
    expect(b.selectedField?.label).toBe('Heading')

    b.updateField('title', { fieldname: 'heading' })
    expect(names(b)).toEqual(['heading'])
    expect(b.selectedFieldName).toBe('heading')
  })

  it('updateField retypes a field, keeping its other props and selection', () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'amount', label: 'Amount', fieldtype: 'Data', options: 'a\nb', required: true },
    ])
    b.selectField('amount')

    b.updateField('amount', { fieldtype: 'Int' })

    expect(b.selectedField?.fieldtype).toBe('Int')
    // no cleanup - sibling props are left intact by design
    expect(b.selectedField?.options).toBe('a\nb')
    expect(b.selectedField?.required).toBe(true)
    expect(b.selectedFieldName).toBe('amount')
  })

  it('removeField drops the field and clears an orphaned selection', async () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'a', label: 'A', fieldtype: 'Data' },
      { fieldname: 'b', label: 'B', fieldtype: 'Data' },
    ])
    b.selectField('b')

    b.removeField('b')
    await nextTick()

    expect(names(b)).toEqual(['a'])
    expect(b.selectedFieldName).toBeNull()
  })

  it('removeField keeps a still-valid selection', async () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'a', label: 'A', fieldtype: 'Data' },
      { fieldname: 'b', label: 'B', fieldtype: 'Data' },
    ])
    b.selectField('a')

    b.removeField('b')
    await nextTick()

    expect(b.selectedFieldName).toBe('a')
  })
})

describe('builder store — tabs', () => {
  it('addTab appends a Tab + Section pair', () => {
    const b = useBuilderStore()
    b.doctype = seed([{ fieldname: 'title', label: 'Title', fieldtype: 'Data' }])

    b.addTab()

    const fields = b.doctype!.fields
    expect(fields.map((f) => f.fieldtype)).toEqual(['Data', 'Tab', 'Section'])
    expect(fields[1].label).toBe('New Tab')
  })

  it('addTab(after) inserts the new tab right after the named tab', () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'tab_one', label: 'One', fieldtype: 'Tab' },
      { fieldname: 'f1', label: 'F1', fieldtype: 'Data' },
      { fieldname: 'tab_two', label: 'Two', fieldtype: 'Tab' },
      { fieldname: 'f2', label: 'F2', fieldtype: 'Data' },
    ])

    b.addTab('tab_one')

    const idxNew = b.doctype!.fields.findIndex((f) => f.label === 'New Tab')
    const idxTwo = b.doctype!.fields.findIndex((f) => f.fieldname === 'tab_two')
    expect(idxNew).toBeGreaterThan(0)
    expect(idxNew).toBeLessThan(idxTwo)
  })

  it('removeTab drops the tab and everything under it', () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'tab_one', label: 'One', fieldtype: 'Tab' },
      { fieldname: 'f1', label: 'F1', fieldtype: 'Data' },
      { fieldname: 'tab_two', label: 'Two', fieldtype: 'Tab' },
      { fieldname: 'f2', label: 'F2', fieldtype: 'Data' },
    ])

    b.removeTab('tab_one')

    expect(names(b)).toEqual(['tab_two', 'f2'])
  })
})

describe('builder store — sections & columns', () => {
  it('addSection appends a Section to the target tab', () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'tab_one', label: 'One', fieldtype: 'Tab' },
      { fieldname: 'sec_a', label: 'A', fieldtype: 'Section' },
      { fieldname: 'f1', label: 'F1', fieldtype: 'Data' },
    ])

    b.addSection('tab_one')

    const types = b.doctype!.fields.map((f) => f.fieldtype)
    expect(types).toEqual(['Tab', 'Section', 'Data', 'Section'])
  })

  it('removeSection drops the section and its fields', () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'sec_a', label: 'A', fieldtype: 'Section' },
      { fieldname: 'f1', label: 'F1', fieldtype: 'Data' },
      { fieldname: 'sec_b', label: 'B', fieldtype: 'Section' },
      { fieldname: 'f2', label: 'F2', fieldtype: 'Data' },
    ])

    b.removeSection('sec_a')

    expect(names(b)).toEqual(['sec_b', 'f2'])
  })

  it('setSectionColumns grows by inserting Column breaks and shrinks by merging', () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'sec_a', label: 'A', fieldtype: 'Section' },
      { fieldname: 'f1', label: 'F1', fieldtype: 'Data' },
      { fieldname: 'f2', label: 'F2', fieldtype: 'Data' },
    ])

    b.setSectionColumns('sec_a', 2)
    expect(b.doctype!.fields.filter((f) => f.fieldtype === 'Column')).toHaveLength(1)

    b.setSectionColumns('sec_a', 1)
    expect(b.doctype!.fields.filter((f) => f.fieldtype === 'Column')).toHaveLength(0)
    // no field is lost when collapsing columns
    expect(names(b)).toEqual(['sec_a', 'f1', 'f2'])
  })

  it('addFieldToColumn inserts into the target column and selects the new field', () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'sec_a', label: 'A', fieldtype: 'Section' },
      { fieldname: 'f1', label: 'F1', fieldtype: 'Data' },
      { fieldname: 'col_b', label: '', fieldtype: 'Column' },
      { fieldname: 'f2', label: 'F2', fieldtype: 'Data' },
    ])

    b.addFieldToColumn('Data', 'sec_a', 0)

    // new field lands in column 0 - before the column break
    const fields = b.doctype!.fields
    const colBreak = fields.findIndex((f) => f.fieldtype === 'Column')
    const newIdx = fields.findIndex((f) => f.fieldname === b.selectedFieldName)
    expect(newIdx).toBeGreaterThan(-1)
    expect(newIdx).toBeLessThan(colBreak)
  })

  it('addFieldToColumn falls back to appending when the section is unknown', () => {
    const b = useBuilderStore()
    b.doctype = seed([{ fieldname: 'f1', label: 'F1', fieldtype: 'Data' }])

    b.addFieldToColumn('Data', 'does_not_exist', 0)

    expect(names(b)).toEqual(['f1', 'data_field'])
    expect(b.selectedFieldName).toBe('data_field')
  })
})

describe('builder store — promoteImplicitSection', () => {
  it('turns an implicit section into a real Section field', () => {
    const b = useBuilderStore()
    b.doctype = seed([
      { fieldname: 'tab_one', label: 'One', fieldtype: 'Tab' },
      { fieldname: 'f1', label: 'F1', fieldtype: 'Data' },
    ])

    const implicit = b.layout[0].sections[0]._fieldname
    expect(implicit.startsWith('__')).toBe(true)

    const promoted = b.promoteImplicitSection(implicit)

    expect(promoted).not.toBe(implicit)
    const secField = b.doctype!.fields.find((f) => f.fieldname === promoted)
    expect(secField?.fieldtype).toBe('Section')
  })
})
