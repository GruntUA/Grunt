import { nextTick, ref, type Ref } from 'vue'

import { getNonPhysicalTypeSet } from '@/core/fieldRegistry'
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

    // 1. Find which tab this field is in
    if (params.activeTab && params.dt.value) {
      let fieldTab = 'Main'
      for (const field of params.dt.value.fields) {
        if (field.fieldtype === 'Tab') {
          fieldTab = field.label || 'Main'
        }
        if (field.fieldname === firstKey) {
          if (params.activeTab.value !== fieldTab) {
            params.activeTab.value = fieldTab
          }
          break
        }
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
