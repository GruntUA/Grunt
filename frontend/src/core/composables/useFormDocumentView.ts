import { computed, type Ref } from 'vue'

import type { DocType } from '@/types'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

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
      return params.id ? '...' : t('New {doctype}', { doctype: params.dt.value?.label ?? '' })
    }

    // A singleton is one settings-like record: its id means nothing to people.
    if (params.dt.value?.is_singleton) return params.dt.value.label

    const titleField = params.dt.value?.title_field

    const titleValue = titleField ? params.document.value[titleField] : undefined
    const nameValue = params.document.value.name
    return (titleValue as string) || (nameValue as string) || t('New {doctype}', { doctype: params.dt.value?.label ?? '' })
  })

  function onFormUpdate(updated: Record<string, unknown>) {
    // A Button field's "value" is just a click (a timestamp): it fires
    // on_change but never lands in the document - or the form would turn
    // unsaved on every click.
    const buttons = new Set(
      (params.dt.value?.fields ?? []).filter((f) => f.fieldtype === 'Button').map((f) => f.fieldname),
    )
    const changedFields: string[] = []
    const values: Record<string, unknown> = {}
    for (const key of Object.keys(updated)) {
      if (buttons.has(key)) {
        if (updated[key] !== undefined && updated[key] !== params.form.value[key]) changedFields.push(key)
        continue
      }
      values[key] = updated[key]
      if (updated[key] !== params.form.value[key]) {
        changedFields.push(key)
      }
    }

    Object.assign(params.form.value, values)
    for (const field of changedFields) {
      params.runOnChange(field)
    }
  }

  return {
    docTitle,
    onFormUpdate,
  }
}
