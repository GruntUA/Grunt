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
      applyHistoryObject(params.form.value, 'duplicate')
      applyHistoryObject(params.form.value, 'initial_data')
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
