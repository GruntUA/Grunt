import { nextTick, ref, type Ref } from 'vue'

import { getNonPhysicalTypeSet } from '@/core/fieldRegistry'
import { parseLayout } from '@/core/composables/useFormLayout'
import type { DocType } from '@/types'

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

  function focusFirstError() {
    const firstKey = Object.keys(validationErrors.value)[0]
    if (!firstKey) return

    // 1. Switch to the tab that contains this field (tabs are keyed by fieldname)
    if (params.activeTab && params.dt.value) {
      const layout = parseLayout(params.dt.value.fields)
      const target = layout.find((t) =>
        t.sections.some((s) => s.columns.some((c) => c.some((f) => f.fieldname === firstKey))),
      )
      if (target && params.activeTab.value !== target._fieldname) {
        params.activeTab.value = target._fieldname
      }
    }

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

  function validateForm(): boolean {
    resetValidationErrors()

    if (!params.dt.value) {
      return true
    }

    const nonPhysical = getNonPhysicalTypeSet()
    for (const field of params.dt.value.fields) {
      if (nonPhysical.has(field.fieldtype)) continue
      if (params.displayOverrides[field.fieldname] === false) continue

      const isRequired = params.reqdOverrides[field.fieldname] !== undefined
        ? params.reqdOverrides[field.fieldname]
        : field.required

      if (!isRequired) continue

      const value = params.form.value[field.fieldname]
      if (value === null || value === undefined || value === '') {
        validationErrors.value[field.fieldname] = `Поле "${field.label}" є обов'язковим`
      }
    }

    // DocType core schema has required fields on backend model level
    // that may not always be marked as `required` in form metadata.
    if (params.doctype === 'DocType') {
      const requiredCore: Array<{ key: 'name' | 'label' | 'module'; label: string }> = [
        { key: 'name', label: 'Назва' },
        { key: 'label', label: 'Мітка' },
        { key: 'module', label: 'Модуль' },
      ]
      for (const core of requiredCore) {
        const value = params.form.value[core.key]
        if (value === null || value === undefined || value === '') {
          validationErrors.value[core.key] = `Поле "${core.label}" є обов'язковим`
        }
      }
    }

    if (Object.keys(validationErrors.value).length > 0) {
      const coreLabels: Record<string, string> = {
        name: 'Назва',
        label: 'Мітка',
        module: 'Модуль',
      }
      const missingLabels = Object.keys(validationErrors.value)
        .map((fieldname) => coreLabels[fieldname] || params.dt.value?.fields.find((f) => f.fieldname === fieldname)?.label || fieldname)
        .join(', ')

      params.toast.error(`Заповніть обов'язкові поля: ${missingLabels}`)
      focusFirstError()
      return false
    }

    return true
  }

  return {
    validationErrors,
    resetValidationErrors,
    focusFirstError,
    validateForm,
  }
}
