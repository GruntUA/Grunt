import type { Ref } from 'vue'
import type { Router } from 'vue-router'

import { clearScriptCache } from '@/core/scripting/executor'
import type { DocType } from '@/types'
import type { QueryClient } from '@tanstack/vue-query'

interface UseFormSaveParams {
  doctype: string
  id: string | null
  workspace?: string
  dt: Ref<DocType | null>
  validationErrors: Ref<Record<string, string>>
  save: () => Promise<unknown>
  runScriptEvent: (event: 'validate' | 'before_save' | 'after_save', changedField?: string) => Promise<boolean>
  validateForm: () => boolean
  focusFirstError: () => void
  markAllowLeave: () => void
  finishLinkCreate: (doctype: string, docname: string) => boolean
  queryClient: QueryClient
  dtStore: { invalidate: (doctype: string) => void }
  router: Router
  toast: {
    success: (message: string) => void
    error: (message: string) => void
  }
}

export function useFormSave(params: UseFormSaveParams) {
  async function handleSave() {
    params.validationErrors.value = {}

    if (!params.validateForm()) {
      return
    }

    const valid = await params.runScriptEvent('validate')
    if (valid === false) return

    await params.runScriptEvent('before_save')

    try {
      const saved = await params.save()
      params.toast.success('Збережено')
      void params.runScriptEvent('after_save')
      params.dtStore.invalidate(params.doctype)
      params.queryClient.invalidateQueries({ queryKey: ['documents', params.doctype] })

      if (params.doctype === 'ClientScript') {
        clearScriptCache()
      }

      if (!params.id) {
        params.markAllowLeave()
        const savedDoc = saved as { id: string; name: string }

        if (params.finishLinkCreate(params.doctype, savedDoc.name)) {
          return
        }

        const path = params.workspace
          ? `/${params.workspace}/${params.doctype}/${savedDoc.id}`
          : `/${params.doctype}/${savedDoc.id}`
        params.router.replace(path)
      }
    } catch (error: unknown) {
      const err = error as { response?: { status?: number; data?: { detail?: string | string[] } } }
      if (err?.response?.status === 422) {
        const detail = err.response.data?.detail
        const details: string[] = Array.isArray(detail)
          ? detail
          : (typeof detail === 'string' ? [detail] : [])

        let hasFieldErrors = false
        for (const item of details) {
          const match = item.match(/^([a-zA-Z0-9_]+):\s*(.+)$/)
          if (!match) continue

          params.validationErrors.value[match[1]] = match[2]
          hasFieldErrors = true
        }

        if (hasFieldErrors) {
          params.toast.error('Перевірте правильність заповнення')
          params.focusFirstError()
        } else if (details.length > 0) {
          params.toast.error(details.join('; '))
        } else {
          params.toast.error('Помилка валідації')
        }
        return
      }

      params.toast.error('Помилка збереження')
    }
  }

  return {
    handleSave,
  }
}
