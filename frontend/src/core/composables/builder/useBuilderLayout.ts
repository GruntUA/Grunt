import type { Ref } from 'vue'
import { parseLayout, flattenLayout } from '@/core/composables/useFormLayout'
import type { FormLayout, LayoutSection, LayoutTab } from '@/core/composables/useFormLayout'
import type { DocType, DocField, FieldType } from '@/types'

interface UseBuilderLayoutParams {
  doctype: Ref<DocType | null>
  /** Set the current field selection by fieldname (or clear it). */
  selectField: (fieldname: string | null) => void
}

/**
 * Layout mutations for the designer canvas.
 *
 * Every structural change follows the same shape: parse the flat `fields` array
 * into a `FormLayout` tree, mutate the tree, then flatten it back. No ad-hoc
 * splicing of the flat array — the tree is the single mental model. Orphaned
 * field selections are cleaned up by a watcher in the builder store.
 */
export function useBuilderLayout({ doctype, selectField }: UseBuilderLayoutParams) {
  function generateFieldname(fieldtype: string, reserved: Iterable<string> = []): string {
    const base = fieldtype.toLowerCase().replace(/[^a-z]/g, '') + '_field'
    const taken = new Set((doctype.value?.fields ?? []).map((f) => f.fieldname))
    for (const r of reserved) taken.add(r)
    if (!taken.has(base)) return base
    let i = 2
    while (taken.has(`${base}_${i}`)) i++
    return `${base}_${i}`
  }

  function newSection(label = ''): LayoutSection {
    const fieldname = generateFieldname('Section')
    return {
      type: 'section',
      label,
      collapsible: false,
      collapsed: false,
      _fieldname: fieldname,
      _field: { fieldname, label, fieldtype: 'Section' },
      _columnFieldnames: [],
      columns: [[]],
    }
  }

  /** Parse → mutate → flatten → commit as a fresh `fields` array. */
  function commit<T>(mutate: (layout: FormLayout) => T): T | undefined {
    if (!doctype.value) return undefined
    const layout = parseLayout(doctype.value.fields ?? [])
    const result = mutate(layout)
    doctype.value = { ...doctype.value, fields: flattenLayout(layout) }
    return result
  }

  function rebuildFlatFields(newLayout: FormLayout) {
    if (!doctype.value) return
    doctype.value = { ...doctype.value, fields: flattenLayout(newLayout) }
  }

  function addTab(afterTabFieldname?: string) {
    commit((layout) => {
      const fieldname = generateFieldname('Tab')
      const tab: LayoutTab = {
        type: 'tab',
        label: 'New Tab',
        _fieldname: fieldname,
        _field: { fieldname, label: 'New Tab', fieldtype: 'Tab' },
        sections: [newSection()],
      }
      const at = afterTabFieldname
        ? layout.findIndex((t) => t._fieldname === afterTabFieldname)
        : -1
      if (at === -1) layout.push(tab)
      else layout.splice(at + 1, 0, tab)
    })
  }

  function removeTab(tabFieldname: string) {
    commit((layout) => {
      const i = layout.findIndex((t) => t._fieldname === tabFieldname)
      if (i !== -1) layout.splice(i, 1)
    })
  }

  function addSection(tabFieldname: string) {
    commit((layout) => {
      const tab =
        layout.find((t) => t._fieldname === tabFieldname) ?? layout[layout.length - 1]
      tab?.sections.push(newSection())
    })
  }

  function promoteImplicitSection(implicitFieldname: string): string {
    return (
      commit((layout) => {
        for (const tab of layout) {
          for (const section of tab.sections) {
            if (section._fieldname !== implicitFieldname || section._field) continue
            const fieldname = generateFieldname('Section')
            section._fieldname = fieldname
            section._field = { fieldname, label: section.label, fieldtype: 'Section' }
            return fieldname
          }
        }
        return implicitFieldname
      }) ?? implicitFieldname
    )
  }

  function removeSection(sectionFieldname: string) {
    commit((layout) => {
      for (const tab of layout) {
        const i = tab.sections.findIndex((s) => s._fieldname === sectionFieldname)
        if (i !== -1) {
          tab.sections.splice(i, 1)
          return
        }
      }
    })
  }

  function setSectionColumns(sectionFieldname: string, count: number) {
    if (count < 1 || count > 4) return
    commit((layout) => {
      for (const tab of layout) {
        for (const section of tab.sections) {
          if (section._fieldname !== sectionFieldname) continue
          const current = section.columns.length
          if (count > current) {
            for (let i = current; i < count; i++) {
              section._columnFieldnames.push(
                generateFieldname('Column', section._columnFieldnames),
              )
              section.columns.push([])
            }
          } else if (count < current) {
            const lastKept = section.columns[count - 1]
            for (let i = count; i < current; i++) lastKept.push(...section.columns[i])
            section.columns.splice(count)
            section._columnFieldnames.splice(count - 1)
          }
          return
        }
      }
    })
  }

  function addFieldToColumn(
    fieldtype: FieldType,
    sectionFieldname: string,
    columnIndex: number,
  ) {
    const fieldname = generateFieldname(fieldtype)
    const newField: DocField = { fieldname, label: fieldtype, fieldtype }

    const inserted = commit((layout) => {
      for (const tab of layout) {
        for (const section of tab.sections) {
          if (section._fieldname !== sectionFieldname) continue
          const col = section.columns[columnIndex]
          if (!col) return false
          col.push(newField)
          return true
        }
      }
      return false
    })

    if (!inserted && doctype.value) {
      doctype.value = { ...doctype.value, fields: [...doctype.value.fields, newField] }
    }
    selectField(fieldname)
  }

  return {
    generateFieldname,
    rebuildFlatFields,
    addTab,
    removeTab,
    addSection,
    promoteImplicitSection,
    removeSection,
    setSectionColumns,
    addFieldToColumn,
  }
}
