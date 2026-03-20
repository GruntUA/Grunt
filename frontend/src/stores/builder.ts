import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { DocType, DocField, FieldType } from '@/types'
import { metaApi } from '@/core/api'

export const useBuilderStore = defineStore('builder', () => {
  const doctype = ref<DocType | null>(null)
  const isDirty = ref(false)
  const selectedFieldIndex = ref<number | null>(null)
  const isSaving = ref(false)

  async function loadDocType(name: string) {
    doctype.value = await metaApi.get(name)
    isDirty.value = false
    selectedFieldIndex.value = null
  }

  function generateFieldname(fieldtype: string): string {
    const base = fieldtype.toLowerCase().replace(/[^a-z]/g, '') + '_field'
    const existing = new Set((doctype.value?.fields ?? []).map((f) => f.fieldname))
    if (!existing.has(base)) return base
    let i = 2
    while (existing.has(`${base}_${i}`)) i++
    return `${base}_${i}`
  }

  function addField(fieldtype: FieldType, afterIndex?: number) {
    if (!doctype.value) return
    const newField: DocField = {
      fieldname: generateFieldname(fieldtype),
      label: fieldtype,
      fieldtype,
    }
    const idx = afterIndex !== undefined ? afterIndex + 1 : doctype.value.fields.length
    doctype.value.fields.splice(idx, 0, newField)
    selectedFieldIndex.value = idx
    isDirty.value = true
  }

  function removeField(index: number) {
    if (!doctype.value) return
    doctype.value.fields.splice(index, 1)
    if (selectedFieldIndex.value === index) selectedFieldIndex.value = null
    else if (selectedFieldIndex.value !== null && selectedFieldIndex.value > index) {
      selectedFieldIndex.value--
    }
    isDirty.value = true
  }

  function moveField(fromIndex: number, toIndex: number) {
    if (!doctype.value) return
    const [field] = doctype.value.fields.splice(fromIndex, 1)
    doctype.value.fields.splice(toIndex, 0, field)
    selectedFieldIndex.value = toIndex
    isDirty.value = true
  }

  function updateField(index: number, patch: Partial<DocField>) {
    if (!doctype.value) return
    doctype.value.fields[index] = { ...doctype.value.fields[index], ...patch }
    isDirty.value = true
  }

  function updateDocType(patch: Partial<DocType>) {
    if (!doctype.value) return
    doctype.value = { ...doctype.value, ...patch }
    isDirty.value = true
  }

  function selectField(index: number | null) {
    selectedFieldIndex.value = index
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

  return {
    doctype,
    isDirty,
    selectedFieldIndex,
    isSaving,
    loadDocType,
    addField,
    removeField,
    moveField,
    updateField,
    updateDocType,
    selectField,
    save,
  }
})
