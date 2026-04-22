import { nextTick, ref, type Ref } from 'vue'

import { getNonPhysicalTypeSet } from '@/core/fieldRegistry'
import type { DocType } from '@/types'

interface UseFormValidationParams {
  dt: Ref<DocType | null>
  form: Ref<Record<string, unknown>>
  displayOverrides: Record<string, boolean>
  reqdOverrides: Record<string, boolean>
  toast: { error: (message: string) => void }
}

export function useFormValidation(params: UseFormValidationParams) {
  const validationErrors = ref<Record<string, string>>({})

  function resetValidationErrors() {
    validationErrors.value = {}
  }

  function focusFirstError() {
    nextTick(() => {
      const firstKey = Object.keys(validationErrors.value)[0]
      if (!firstKey) return

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

    if (Object.keys(validationErrors.value).length > 0) {
      params.toast.error("Заповніть обов'язкові поля")
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
