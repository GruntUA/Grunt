import type { Ref } from 'vue'
import { parseLayout, flattenLayout } from '@/core/composables/useFormLayout'
import type { FormLayout } from '@/core/composables/useFormLayout'
import type { DocType, DocField, FieldType } from '@/types'

interface UseBuilderLayoutParams {
  doctype: Ref<DocType | null>
  isDirty: Ref<boolean>
  selectedFieldIdx: Ref<number | null>
}

export function useBuilderLayout({ doctype, isDirty, selectedFieldIdx }: UseBuilderLayoutParams) {
  function generateFieldname(fieldtype: string): string {
    const base = fieldtype.toLowerCase().replace(/[^a-z]/g, '') + '_field'
    const existing = new Set((doctype.value?.fields ?? []).map((f) => f.fieldname))
    if (!existing.has(base)) return base
    let i = 2
    while (existing.has(`${base}_${i}`)) i++
    return `${base}_${i}`
  }

  function normalizeFields() {
    if (doctype.value && !Array.isArray(doctype.value.fields)) {
      doctype.value.fields = []
    }
  }

  function rebuildFlatFields(newLayout: FormLayout) {
    if (!doctype.value) return
    doctype.value.fields = flattenLayout(newLayout)
    isDirty.value = true
  }

  function addTab(afterTabFieldname?: string) {
    if (!doctype.value) return
    normalizeFields()
    const tabField: DocField = {
      fieldname: generateFieldname('Tab'),
      label: 'New Tab',
      fieldtype: 'Tab',
    }
    const sectionField: DocField = {
      fieldname: generateFieldname('Section'),
      label: '',
      fieldtype: 'Section',
    }

    if (afterTabFieldname) {
      const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === afterTabFieldname)
      if (tabIdx === -1) {
        doctype.value.fields = [...doctype.value.fields, tabField, sectionField]
      } else {
        let endIdx = doctype.value.fields.length
        for (let i = tabIdx + 1; i < doctype.value.fields.length; i++) {
          if (doctype.value.fields[i].fieldtype === 'Tab') {
            endIdx = i
            break
          }
        }
        const newFields = [...doctype.value.fields]
        newFields.splice(endIdx, 0, tabField, sectionField)
        doctype.value.fields = newFields
      }
    } else {
      doctype.value.fields = [...doctype.value.fields, tabField, sectionField]
    }
    isDirty.value = true
  }

  function removeTab(tabFieldname: string) {
    if (!doctype.value) return
    normalizeFields()
    const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === tabFieldname)
    if (tabIdx === -1) return

    let endIdx = doctype.value.fields.length
    for (let i = tabIdx + 1; i < doctype.value.fields.length; i++) {
      if (doctype.value.fields[i].fieldtype === 'Tab') {
        endIdx = i
        break
      }
    }

    const newFields = [...doctype.value.fields]
    const removed = newFields.splice(tabIdx, endIdx - tabIdx)
    doctype.value.fields = newFields
    if (selectedFieldIdx.value !== null && selectedFieldIdx.value >= tabIdx && selectedFieldIdx.value < tabIdx + removed.length) {
      selectedFieldIdx.value = null
    } else if (selectedFieldIdx.value !== null && selectedFieldIdx.value >= tabIdx + removed.length) {
      selectedFieldIdx.value -= removed.length
    }
    isDirty.value = true
  }

  function addSection(tabFieldname: string) {
    if (!doctype.value) return
    normalizeFields()
    const sectionField: DocField = {
      fieldname: generateFieldname('Section'),
      label: '',
      fieldtype: 'Section',
    }

    const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === tabFieldname)
    let endIdx = doctype.value.fields.length
    if (tabIdx !== -1) {
      for (let i = tabIdx + 1; i < doctype.value.fields.length; i++) {
        if (doctype.value.fields[i].fieldtype === 'Tab') {
          endIdx = i
          break
        }
      }
    }

    const newFields = [...doctype.value.fields]
    newFields.splice(endIdx, 0, sectionField)
    doctype.value.fields = newFields
    isDirty.value = true
  }

  function promoteImplicitSection(implicitFieldname: string): string {
    if (!doctype.value) return implicitFieldname
    normalizeFields()
    const currentLayout = parseLayout(doctype.value.fields)
    for (const tab of currentLayout) {
      for (const section of tab.sections) {
        if (section._fieldname !== implicitFieldname || section._field) continue
        const fieldname = generateFieldname('Section')
        const sectionField: DocField = { fieldname, label: section.label, fieldtype: 'Section' }
        let insertIdx: number
        if (tab._field) {
          const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === tab._fieldname)
          insertIdx = tabIdx + 1
        } else {
          insertIdx = 0
        }
        const newFields = [...doctype.value.fields]
        newFields.splice(insertIdx, 0, sectionField)
        doctype.value.fields = newFields
        isDirty.value = true
        return fieldname
      }
    }
    return implicitFieldname
  }

  function removeSection(sectionFieldname: string) {
    if (!doctype.value) return
    normalizeFields()
    const secIdx = doctype.value.fields.findIndex((f) => f.fieldname === sectionFieldname)
    if (secIdx === -1) return

    let endIdx = doctype.value.fields.length
    for (let i = secIdx + 1; i < doctype.value.fields.length; i++) {
      if (doctype.value.fields[i].fieldtype === 'Section' || doctype.value.fields[i].fieldtype === 'Tab') {
        endIdx = i
        break
      }
    }

    const newFields = [...doctype.value.fields]
    const removed = newFields.splice(secIdx, endIdx - secIdx)
    doctype.value.fields = newFields
    if (selectedFieldIdx.value !== null && selectedFieldIdx.value >= secIdx && selectedFieldIdx.value < secIdx + removed.length) {
      selectedFieldIdx.value = null
    } else if (selectedFieldIdx.value !== null && selectedFieldIdx.value >= secIdx + removed.length) {
      selectedFieldIdx.value -= removed.length
    }
    isDirty.value = true
  }

  function setSectionColumns(sectionFieldname: string, count: number) {
    if (!doctype.value || count < 1 || count > 4) return
    normalizeFields()
    const currentLayout = parseLayout(doctype.value.fields)

    for (const tab of currentLayout) {
      for (const section of tab.sections) {
        if (section._fieldname !== sectionFieldname) continue

        const currentCount = section.columns.length

        if (count > currentCount) {
          for (let i = currentCount; i < count; i++) {
            section._columnFieldnames.push(generateFieldname('Column'))
            section.columns.push([])
          }
        } else if (count < currentCount) {
          const lastKeptCol = section.columns[count - 1]
          for (let i = count; i < currentCount; i++) {
            lastKeptCol.push(...section.columns[i])
          }
          section.columns.splice(count)
          section._columnFieldnames.splice(count - 1)
        }

        doctype.value.fields = flattenLayout(currentLayout)
        isDirty.value = true
        return
      }
    }
  }

  function addFieldToColumn(fieldtype: FieldType, sectionFieldname: string, columnIndex: number) {
    if (!doctype.value) return
    normalizeFields()
    const newField: DocField = {
      fieldname: generateFieldname(fieldtype),
      label: fieldtype,
      fieldtype,
    }

    const currentLayout = parseLayout(doctype.value.fields)
    for (const tab of currentLayout) {
      for (const section of tab.sections) {
        if (section._fieldname === sectionFieldname) {
          const col = section.columns[columnIndex]
          if (col) {
            col.push(newField)
            doctype.value.fields = flattenLayout(currentLayout)
            selectedFieldIdx.value = doctype.value.fields.findIndex((f) => f.fieldname === newField.fieldname)
            isDirty.value = true
            return
          }
        }
      }
    }

    doctype.value.fields = [...doctype.value.fields, newField]
    selectedFieldIdx.value = doctype.value.fields.length - 1
    isDirty.value = true
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
