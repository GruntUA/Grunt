import { nextTick, ref, type Ref } from 'vue'

import { getNonPhysicalTypeSet } from '@/core/fieldRegistry'
import { parseLayout } from '@/core/composables/useFormLayout'
import { cellError } from '@/components/fields/Table/useTableCell'
import { useDocTypeStore } from '@/stores/doctype'
import type { DocField, DocType } from '@/types'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

interface UseFormValidationParams {
  doctype: string
  dt: Ref<DocType | null>
  form: Ref<Record<string, unknown>>
  displayOverrides: Record<string, boolean>
  reqdOverrides: Record<string, boolean>
  toast: { error: (message: string) => void }
  activeTab?: Ref<string>
}

export function useFormValidation(params: UseFormValidationParams) {
  const validationErrors = ref<Record<string, string>>({})

  function resetValidationErrors() {
    validationErrors.value = {}
  }

  /** Open the tab that holds *fieldname* (tabs are keyed by fieldname); its element is rendered after nextTick. */
  function revealField(fieldname: string) {
    if (!params.activeTab || !params.dt.value) return
    const layout = parseLayout(params.dt.value.fields)
    const target = layout.find((t) =>
      t.sections.some((s) => s.columns.some((c) => c.some((f) => f.fieldname === fieldname))),
    )
    if (target && params.activeTab.value !== target._fieldname) {
      params.activeTab.value = target._fieldname
    }
  }

  function focusFirstError() {
    const firstKey = Object.keys(validationErrors.value)[0]
    if (!firstKey) return

    revealField(firstKey)

    nextTick(() => {
      const el = window.document.querySelector(`[data-fieldname="${firstKey}"]`) as HTMLElement | null
      if (!el) return

      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('field-shake')
      el.addEventListener('animationend', () => el.classList.remove('field-shake'), { once: true })

      const input = el.querySelector('input, textarea, select, [contenteditable]') as HTMLElement | null
      input?.focus()
    })
  }

  /**
   * First invalid cell of a child table, as "Row 2: Qty - Required". The child
   * schema comes from the DocType store cache the Table field fills when it
   * renders; a table not rendered yet is left to the server check.
   */
  function tableError(field: DocField, rows: unknown, nonPhysicalTypes: Set<string>): string | null {
    const child = field.options ? useDocTypeStore().cache.get(field.options) : undefined
    if (!child || !Array.isArray(rows)) return null
    const childFields = child.fields.filter((f) => !nonPhysicalTypes.has(f.fieldtype) && !f.hidden)
    for (const [i, row] of rows.entries()) {
      for (const f of childFields) {
        const error = cellError(row as Record<string, unknown>, f)
        if (error) return t('Row {row}: {field} - {error}', { row: i + 1, field: f.label || f.fieldname, error })
      }
    }
    return null
  }

  function validateForm(): boolean {
    resetValidationErrors()

    if (!params.dt.value) {
      return true
    }

    const nonPhysicalTypes = getNonPhysicalTypeSet()
    const tableErrors: Record<string, string> = {}
    for (const field of params.dt.value.fields) {
      if (params.displayOverrides[field.fieldname] === false) continue
      if (field.fieldtype === 'Table') {
        const error = tableError(field, params.form.value[field.fieldname], nonPhysicalTypes)
        if (error) tableErrors[field.fieldname] = error
      }
      if (nonPhysicalTypes.has(field.fieldtype)) continue

      const isRequired = params.reqdOverrides[field.fieldname] !== undefined
        ? params.reqdOverrides[field.fieldname]
        : field.required

      if (!isRequired) continue

      const value = params.form.value[field.fieldname]
      if (value === null || value === undefined || value === '') {
        validationErrors.value[field.fieldname] = t('Field "{label}" is required', { label: field.label })
      }
    }

    // DocType core schema has required fields on backend model level
    // that may not always be marked as `required` in form metadata.
    if (params.doctype === 'DocType') {
      const requiredCore: Array<{ key: 'name' | 'label' | 'module'; label: string }> = [
        { key: 'name', label: t('Name') },
        { key: 'label', label: t('Label') },
        { key: 'module', label: t('Module') },
      ]
      for (const core of requiredCore) {
        const value = params.form.value[core.key]
        if (value === null || value === undefined || value === '') {
          validationErrors.value[core.key] = t('Field "{label}" is required', { label: core.label })
        }
      }
    }

    if (Object.keys(validationErrors.value).length === 0 && Object.keys(tableErrors).length > 0) {
      validationErrors.value = tableErrors
      const [fieldname, error] = Object.entries(tableErrors)[0]
      const label = params.dt.value.fields.find((f) => f.fieldname === fieldname)?.label || fieldname
      params.toast.error(`${label}: ${error}`)
      focusFirstError()
      return false
    }

    if (Object.keys(validationErrors.value).length > 0) {
      const coreLabels: Record<string, string> = {
        name: t('Name'),
        label: t('Label'),
        module: t('Module'),
      }
      const missingLabels = Object.keys(validationErrors.value)
        .map((fieldname) => coreLabels[fieldname] || params.dt.value?.fields.find((f) => f.fieldname === fieldname)?.label || fieldname)
        .join(', ')

      params.toast.error(t('Fill in the required fields: {fields}', { fields: missingLabels }))
      focusFirstError()
      return false
    }

    return true
  }

  return {
    validationErrors,
    resetValidationErrors,
    revealField,
    focusFirstError,
    validateForm,
  }
}
