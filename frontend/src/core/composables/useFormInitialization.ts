import type { Ref } from 'vue'

import type { DocType } from '@/types'

interface LinkDraftResult {
  fieldname: string
  value: string
}

interface FormInitializationParams {
  doctype: string
  id: string | null
  dt: Ref<DocType | null>
  form: Ref<Record<string, unknown>>
  loadDocType: (doctype: string) => Promise<DocType>
  restoreLinkDraft: (
    doctype: string,
    id: string | null,
    form: Record<string, unknown>,
  ) => LinkDraftResult | null
  info: (message: string) => void
  runOnLoad: () => Promise<unknown>
}

function applyHistoryObject(form: Record<string, unknown>, key: 'duplicate' | 'initial_data') {
  const raw = window.history.state?.[key]
  if (!raw) {
    return
  }

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    Object.assign(form, parsed)
  } catch {
    // Ignore malformed history state payloads
  }
}

export function useFormInitialization(params: FormInitializationParams) {
  const initialize = async () => {
    params.dt.value = await params.loadDocType(params.doctype)

    if (!params.id) {
      // Apply field defaults (lowest priority — can be overridden by duplicate/query params)
      for (const field of params.dt.value?.fields ?? []) {
        if (field.default != null && params.form.value[field.fieldname] == null) {
          let val: unknown = field.default
          if (val === 'Today') {
            val = new Date().toISOString().split('T')[0]
          }
          params.form.value[field.fieldname] = val
        }
      }

      applyHistoryObject(params.form.value, 'duplicate')
      applyHistoryObject(params.form.value, 'initial_data')

      // Pre-fill from URL query parameters (e.g. ?parent_department=UUID)
      const query = new URLSearchParams(window.location.search)
      for (const [key, value] of query.entries()) {
        const field = params.dt.value?.fields.find((f: any) => f.fieldname === key)
        if (field) {
          params.form.value[key] = value
        }
      }
    }

    const linkReturn = params.restoreLinkDraft(params.doctype, params.id, params.form.value)
    if (linkReturn) {
      params.form.value[linkReturn.fieldname] = linkReturn.value
      params.info(`Поле встановлено: ${linkReturn.value}`)
    }

    await params.runOnLoad()
  }

  return { initialize }
}
