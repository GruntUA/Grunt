import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { DocType, DocField, FieldType, IndexHint } from '@/types'
import { metaApi } from '@/core/api'
import { parseLayout } from '@/core/composables/useFormLayout'
import type { FormLayout } from '@/core/composables/useFormLayout'
import { useBuilderLayout } from '@/core/composables/builder/useBuilderLayout'

export const useBuilderStore = defineStore('builder', () => {
  const doctype = ref<DocType | null>(null)
  const isDirty = ref(false)
  const isNew = ref(false)
  const _selectedFieldIdx = ref<number | null>(null)
  const isSaving = ref(false)
  const activeTab = ref<string>('form')
  const indexHints = ref<IndexHint[]>([])
  const exportedTo = ref<string | null>(null)

  function resetTransientState() {
    isDirty.value = false
    _selectedFieldIdx.value = null
    activeTab.value = 'form'
    indexHints.value = []
    exportedTo.value = null
  }

  // ── Computed ─────────────────────────────────────────────────────────

  const selectedField = computed<DocField | null>(() => {
    if (_selectedFieldIdx.value === null || !doctype.value) return null
    return doctype.value.fields[_selectedFieldIdx.value] ?? null
  })

  const selectedFieldName = computed<string | null>(() =>
    selectedField.value?.fieldname ?? null
  )

  const layout = computed<FormLayout>(() => {
    const fields = doctype.value?.fields
    if (!Array.isArray(fields)) return []
    return parseLayout(fields)
  })

  // ── Load / Save ──────────────────────────────────────────────────────

  async function loadDocType(name: string) {
    if (name === 'new') {
      doctype.value = { name: '', label: '', module: '', fields: [], permissions: [] }
      isNew.value = true
      resetTransientState()
      return
    }
    doctype.value = await metaApi.get(name)
    isNew.value = false
    resetTransientState()
  }

  async function save(): Promise<DocType | null> {
    if (!doctype.value) return null
    isSaving.value = true
    try {
      const result = isNew.value
        ? await metaApi.create(doctype.value)
        : await metaApi.update(doctype.value)
      if (isNew.value) isNew.value = false
      await metaApi.sync(result.data.name)
      doctype.value = result.data
      indexHints.value = result.hints ?? []
      exportedTo.value = result.exported_to ?? null
      isDirty.value = false
      return result.data
    } finally {
      isSaving.value = false
    }
  }

  const {
    generateFieldname,
    rebuildFlatFields,
    addTab,
    removeTab,
    addSection,
    promoteImplicitSection,
    removeSection,
    setSectionColumns,
    addFieldToColumn,
  } = useBuilderLayout({ doctype, isDirty, selectedFieldIdx: _selectedFieldIdx })

  // ── Selection ────────────────────────────────────────────────────────

  function selectField(fieldname: string | null) {
    if (fieldname === null || !doctype.value) { _selectedFieldIdx.value = null; return }
    const idx = doctype.value.fields.findIndex((f) => f.fieldname === fieldname)
    _selectedFieldIdx.value = idx === -1 ? null : idx
  }

  // ── Field CRUD (by fieldname) ────────────────────────────────────────

  function updateField(fieldname: string, patch: Partial<DocField>) {
    if (!doctype.value) return
    const idx = doctype.value.fields.findIndex((f) => f.fieldname === fieldname)
    if (idx === -1) return

    doctype.value = {
      ...doctype.value,
      fields: doctype.value.fields.map((f, i) => i === idx ? { ...f, ...patch } : f)
    }
    // Index stays the same even if fieldname changed
    isDirty.value = true
  }

  function removeField(fieldname: string) {
    if (!doctype.value) return
    const idx = doctype.value.fields.findIndex((f) => f.fieldname === fieldname)
    if (idx === -1) return

    doctype.value = {
      ...doctype.value,
      fields: doctype.value.fields.filter((_, i) => i !== idx),
    }

    if (_selectedFieldIdx.value === idx) {
      _selectedFieldIdx.value = null
    } else if (_selectedFieldIdx.value !== null && _selectedFieldIdx.value > idx) {
      _selectedFieldIdx.value -= 1
    }
    isDirty.value = true
  }

  function updateDocType(patch: Partial<DocType>) {
    if (!doctype.value) return
    doctype.value = { ...doctype.value, ...patch }
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
    doctype.value = {
      ...doctype.value,
      fields: [...doctype.value.fields, newField]
    }
    _selectedFieldIdx.value = doctype.value.fields.length - 1
    isDirty.value = true
  }

  return {
    doctype,
    isDirty,
    isNew,
    selectedFieldName,
    selectedField,
    isSaving,
    activeTab,
    layout,
    indexHints,
    exportedTo,
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
    promoteImplicitSection,
    removeSection,
    setSectionColumns,
    addFieldToColumn,
  }
})
