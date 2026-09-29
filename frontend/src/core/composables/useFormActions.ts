import type { Ref } from 'vue'
import type { Router } from 'vue-router'

import type { QueryClient } from '@tanstack/vue-query'
import { docUrl } from '@/core/workspaceUrl'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

interface UseFormActionsParams {
  doctype: string
  id: string | null
  workspace?: string
  form: Ref<Record<string, unknown>>
  showDeleteModal: Ref<boolean>
  remove: (replaceWith?: string) => Promise<unknown>
  goToList: () => void
  markAllowLeave: () => void
  router: Router
  queryClient: QueryClient
  toast: {
    success: (message: string) => void
    error: (message: string) => void
  }
}

const PROTECTED_DUPLICATE_FIELDS = [
  'id',
  'name',
  'created_at',
  'updated_at',
  'owner',
  'modified_by',
  'workflow_state',
]

export function useFormActions(params: UseFormActionsParams) {
  function onVersionRestored() {
    params.queryClient.invalidateQueries({ queryKey: ['document', params.doctype, params.id] })
  }

  async function handleDelete(replaceWith?: string) {
    try {
      await params.remove(replaceWith)
      params.toast.success(t('Deleted'))
      params.queryClient.invalidateQueries({ queryKey: ['documents', params.doctype] })
      params.goToList()
    } catch {
      params.toast.error(t('Delete error'))
    }
    params.showDeleteModal.value = false
  }

  function handleDuplicate() {
    const clone = { ...params.form.value }
    PROTECTED_DUPLICATE_FIELDS.forEach((field) => {
      delete clone[field]
    })

    const path = docUrl(params.doctype, 'new', params.workspace)

    params.markAllowLeave()
    params.router.push({ path, state: { duplicate: JSON.stringify(clone) } })
  }

  return {
    onVersionRestored,
    handleDelete,
    handleDuplicate,
  }
}
