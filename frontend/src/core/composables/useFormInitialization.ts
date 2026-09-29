import type { Ref } from 'vue'

import type { DocType } from '@/types'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

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
  /** Looks up a leftover unsaved-changes draft for this (doctype, id) so the form can offer to restore it. */
  checkForDraft: () => void
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

      // Prefill Link fields from the user's is_default User Permissions.
      try {
        const { permissionsApi } = await import('@/core/api/permissions')
        const upDefaults = await permissionsApi.getUserPermissionDefaults(params.doctype)
        for (const [fieldname, value] of Object.entries(upDefaults)) {
          if (params.form.value[fieldname] == null) params.form.value[fieldname] = value
        }
      } catch {
        // no-op — defaults are a convenience, not a requirement
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

      params.checkForDraft()
    }

    const linkReturn = params.restoreLinkDraft(params.doctype, params.id, params.form.value)
    if (linkReturn) {
      params.form.value[linkReturn.fieldname] = linkReturn.value
      params.info(t('Field set: {value}', { value: String(linkReturn.value) }))
    }

    await params.runOnLoad()
  }

  return { initialize }
}
