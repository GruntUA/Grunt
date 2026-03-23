import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { DocType, DocField, FieldType } from '@/types'
import { metaApi } from '@/core/api'
import { parseLayout, flattenLayout } from '@/core/composables/useFormLayout'
import type { FormLayout } from '@/core/composables/useFormLayout'

export const useBuilderStore = defineStore('builder', () => {
  const doctype = ref<DocType | null>(null)
  const isDirty = ref(false)
  const selectedFieldName = ref<string | null>(null)
  const isSaving = ref(false)

  // ── Computed ─────────────────────────────────────────────────────────

  const selectedField = computed<DocField | null>(() => {
    if (!selectedFieldName.value || !doctype.value) return null
    return doctype.value.fields.find((f) => f.fieldname === selectedFieldName.value) ?? null
  })

  const layout = computed<FormLayout>(() => {
    if (!doctype.value) return []
    return parseLayout(doctype.value.fields)
  })

  // ── Load / Save ──────────────────────────────────────────────────────

  async function loadDocType(name: string) {
    doctype.value = await metaApi.get(name)
    isDirty.value = false
    selectedFieldName.value = null
  }

  async function save() {
    if (!doctype.value) return
    isSaving.value = true
    try {
      await metaApi.update(doctype.value)
      await metaApi.sync(doctype.value.name)
      isDirty.value = false
    } finally {
      isSaving.value = false
    }
  }

  // ── Fieldname generator ──────────────────────────────────────────────

  function generateFieldname(fieldtype: string): string {
    const base = fieldtype.toLowerCase().replace(/[^a-z]/g, '') + '_field'
    const existing = new Set((doctype.value?.fields ?? []).map((f) => f.fieldname))
    if (!existing.has(base)) return base
    let i = 2
    while (existing.has(`${base}_${i}`)) i++
    return `${base}_${i}`
  }

  // ── Selection ────────────────────────────────────────────────────────

  function selectField(fieldname: string | null) {
    selectedFieldName.value = fieldname
  }

  // ── Field CRUD (by fieldname) ────────────────────────────────────────

  function updateField(fieldname: string, patch: Partial<DocField>) {
    if (!doctype.value) return
    const idx = doctype.value.fields.findIndex((f) => f.fieldname === fieldname)
    if (idx === -1) return
    doctype.value.fields[idx] = { ...doctype.value.fields[idx], ...patch }
    isDirty.value = true
  }

  function removeField(fieldname: string) {
    if (!doctype.value) return
    const idx = doctype.value.fields.findIndex((f) => f.fieldname === fieldname)
    if (idx === -1) return
    doctype.value.fields.splice(idx, 1)
    if (selectedFieldName.value === fieldname) selectedFieldName.value = null
    isDirty.value = true
  }

  function updateDocType(patch: Partial<DocType>) {
    if (!doctype.value) return
    doctype.value = { ...doctype.value, ...patch }
    isDirty.value = true
  }

  // ── Layout sync ──────────────────────────────────────────────────────

  function rebuildFlatFields(newLayout: FormLayout) {
    if (!doctype.value) return
    doctype.value.fields = flattenLayout(newLayout)
    isDirty.value = true
  }

  // ── Tab operations ───────────────────────────────────────────────────

  function addTab(afterTabFieldname?: string) {
    if (!doctype.value) return
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
      // Find the end of the target tab (next Tab field or end of array)
      const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === afterTabFieldname)
      if (tabIdx === -1) {
        doctype.value.fields.push(tabField, sectionField)
      } else {
        let endIdx = doctype.value.fields.length
        for (let i = tabIdx + 1; i < doctype.value.fields.length; i++) {
          if (doctype.value.fields[i].fieldtype === 'Tab') {
            endIdx = i
            break
          }
        }
        doctype.value.fields.splice(endIdx, 0, tabField, sectionField)
      }
    } else {
      doctype.value.fields.push(tabField, sectionField)
    }
    isDirty.value = true
  }

  function removeTab(tabFieldname: string) {
    if (!doctype.value) return
    const tabIdx = doctype.value.fields.findIndex((f) => f.fieldname === tabFieldname)
    if (tabIdx === -1) return

    // Find the range: from this Tab to the next Tab (or end)
    let endIdx = doctype.value.fields.length
    for (let i = tabIdx + 1; i < doctype.value.fields.length; i++) {
      if (doctype.value.fields[i].fieldtype === 'Tab') {
        endIdx = i
        break
      }
    }

    const removed = doctype.value.fields.splice(tabIdx, endIdx - tabIdx)
    // Deselect if selection was within removed range
    if (selectedFieldName.value && removed.some((f) => f.fieldname === selectedFieldName.value)) {
      selectedFieldName.value = null
    }
    isDirty.value = true
  }

  // ── Section operations ───────────────────────────────────────────────

  function addSection(tabFieldname: string) {
    if (!doctype.value) return
    const sectionField: DocField = {
      fieldname: generateFieldname('Section'),
      label: '',
      fieldtype: 'Section',
    }

    // Find end of the tab
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

    doctype.value.fields.splice(endIdx, 0, sectionField)
    isDirty.value = true
  }

  function removeSection(sectionFieldname: string) {
    if (!doctype.value) return
    const secIdx = doctype.value.fields.findIndex((f) => f.fieldname === sectionFieldname)
    if (secIdx === -1) return

    // Find range: from this Section to next Section/Tab or end
    let endIdx = doctype.value.fields.length
    for (let i = secIdx + 1; i < doctype.value.fields.length; i++) {
      if (doctype.value.fields[i].fieldtype === 'Section' || doctype.value.fields[i].fieldtype === 'Tab') {
        endIdx = i
        break
      }
    }

    const removed = doctype.value.fields.splice(secIdx, endIdx - secIdx)
    if (selectedFieldName.value && removed.some((f) => f.fieldname === selectedFieldName.value)) {
      selectedFieldName.value = null
    }
    isDirty.value = true
  }

  // ── Column operations ────────────────────────────────────────────────

  function setSectionColumns(sectionFieldname: string, count: number) {
    if (!doctype.value || count < 1 || count > 4) return
    const currentLayout = parseLayout(doctype.value.fields)

    for (const tab of currentLayout) {
      for (const section of tab.sections) {
        if (section._fieldname !== sectionFieldname) continue

        const currentCount = section.columns.length

        if (count > currentCount) {
          // Add columns: insert Column break fields + empty column arrays
          for (let i = currentCount; i < count; i++) {
            section._columnFieldnames.push(generateFieldname('Column'))
            section.columns.push([])
          }
        } else if (count < currentCount) {
          // Remove columns from the end, moving orphaned fields to the last kept column
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

  // ── Add field to specific column ─────────────────────────────────────

  function addFieldToColumn(fieldtype: FieldType, sectionFieldname: string, columnIndex: number) {
    if (!doctype.value) return
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
            selectedFieldName.value = newField.fieldname
            isDirty.value = true
            return
          }
        }
      }
    }

    // Fallback: append to end
    doctype.value.fields.push(newField)
    selectedFieldName.value = newField.fieldname
    isDirty.value = true
  }

  // ── Simple add (for palette click) ───────────────────────────────────

  function addField(fieldtype: FieldType) {
    if (!doctype.value) return
    const newField: DocField = {
      fieldname: generateFieldname(fieldtype),
      label: fieldtype,
      fieldtype,
    }
    doctype.value.fields.push(newField)
    selectedFieldName.value = newField.fieldname
    isDirty.value = true
  }

  return {
    doctype,
    isDirty,
    selectedFieldName,
    selectedField,
    isSaving,
    layout,
    loadDocType,
    addField,
    removeField,
    updateField,
    updateDocType,
    selectField,
    save,
    generateFieldname,
    rebuildFlatFields,
    addTab,
    removeTab,
    addSection,
    removeSection,
    setSectionColumns,
    addFieldToColumn,
  }
})
