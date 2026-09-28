import { computed, type Ref } from 'vue'

import type { DocType } from '@/types'
import i18n from '@/plugins/i18n'

const t = (key: string): string => i18n.global.t(key)

interface UseFormDocumentViewParams {
  id: string | null
  dt: Ref<DocType | null>
  document: Ref<Record<string, unknown> | null>
  form: Ref<Record<string, unknown>>
  runOnChange: (field: string) => void
}

export function useFormDocumentView(params: UseFormDocumentViewParams) {
  const docTitle = computed(() => {
    if (!params.document.value) {
      return params.id ? '...' : t('New {doctype}').replace('{doctype}', params.dt.value?.label ?? '')
    }

    const titleField = params.dt.value?.title_field
    if (params.dt.value?.is_singleton && !titleField) {
      return params.dt.value.label
    }

    const titleValue = titleField ? params.document.value[titleField] : undefined
    const nameValue = params.document.value.name
    return (titleValue as string) || (nameValue as string) || t('New {doctype}').replace('{doctype}', params.dt.value?.label ?? '')
  })

  function onFormUpdate(updated: Record<string, unknown>) {
    const changedFields: string[] = []
    for (const key of Object.keys(updated)) {
      if (updated[key] !== params.form.value[key]) {
        changedFields.push(key)
      }
    }

    Object.assign(params.form.value, updated)
    for (const field of changedFields) {
      params.runOnChange(field)
    }
  }

  return {
    docTitle,
    onFormUpdate,
  }
}
