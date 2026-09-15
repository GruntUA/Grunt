import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import type { DocType, DocField, FieldType } from '@/types'
import { parseLayout } from '@/core/composables/useFormLayout'
import type { FormLayout } from '@/core/composables/useFormLayout'
import { useBuilderLayout } from '@/core/composables/builder/useBuilderLayout'
import { computeIndexHints } from '@/core/indexHints'
import type { IndexHint } from '@/types'

/**
 * Designer-only state for the DocType "Конструктор" tab.
 *
 * The document itself (load / save / dirty tracking) is owned by
 * `useFormController` on the surrounding standard form — this store only holds
 * the working copy the canvas mutates and the current field selection, keyed by
 * fieldname so it survives reorders and splices. `DesignerTab.vue` seeds
 * `doctype` on mount and mirrors every change back out via `update:modelValue`.
 */
export const useBuilderStore = defineStore('builder', () => {
  const doctype = ref<DocType | null>(null)
  const selectedFieldName = ref<string | null>(null)

  // ── Selection ────────────────────────────────────────────────────────

  function selectField(fieldname: string | null) {
    if (fieldname === null || !doctype.value) {
      selectedFieldName.value = null
      return
    }
    selectedFieldName.value =
      doctype.value.fields.some((f) => f.fieldname === fieldname) ? fieldname : null
  }

  // Drop a selection whose field was removed by a structural edit.
  watch(
    () => doctype.value?.fields,
    (fields) => {
      if (
        selectedFieldName.value &&
        !(fields ?? []).some((f) => f.fieldname === selectedFieldName.value)
      ) {
        selectedFieldName.value = null
      }
    },
  )

  // ── Computed ─────────────────────────────────────────────────────────

  const selectedField = computed<DocField | null>(() => {
    if (!selectedFieldName.value || !doctype.value) return null
    return doctype.value.fields.find((f) => f.fieldname === selectedFieldName.value) ?? null
  })

  const layout = computed<FormLayout>(() => {
    const fields = doctype.value?.fields
    if (!Array.isArray(fields)) return []
    return parseLayout(fields)
  })

  const indexHints = computed<IndexHint[]>(() => computeIndexHints(doctype.value))

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
  } = useBuilderLayout({ doctype, selectField })

  // ── Field CRUD (by fieldname) ────────────────────────────────────────

  function updateField(fieldname: string, patch: Partial<DocField>) {
    if (!doctype.value) return
    const idx = doctype.value.fields.findIndex((f) => f.fieldname === fieldname)
    if (idx === -1) return

    doctype.value = {
      ...doctype.value,
      fields: doctype.value.fields.map((f, i) => (i === idx ? { ...f, ...patch } : f)),
    }

    // Keep the selection pinned to a field that was just renamed.
    if (patch.fieldname && patch.fieldname !== fieldname && selectedFieldName.value === fieldname) {
      selectedFieldName.value = patch.fieldname
    }
  }

  function removeField(fieldname: string) {
    if (!doctype.value) return
    if (!doctype.value.fields.some((f) => f.fieldname === fieldname)) return

    doctype.value = {
      ...doctype.value,
      fields: doctype.value.fields.filter((f) => f.fieldname !== fieldname),
    }
    // Orphaned selection is cleared by the watcher above.
  }

  function updateDocType(patch: Partial<DocType>) {
    if (!doctype.value) return
    doctype.value = { ...doctype.value, ...patch }
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
      fields: [...doctype.value.fields, newField],
    }
    selectField(newField.fieldname)
  }

  return {
    doctype,
    selectedFieldName,
    selectedField,
    layout,
    indexHints,
    addField,
    removeField,
    updateField,
    updateDocType,
    selectField,
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
