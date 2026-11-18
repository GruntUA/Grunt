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
  /** The values a duplicate starts with (docsApi.getCopy). */
  getCopy: (doctype: string, id: string) => Promise<Record<string, unknown>>
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

  /** "Duplicate": a new form filled from the saved document, minus what a copy
   * doesn't carry (standard columns, `no_copy` fields, workflow state) - the
   * server decides that (grunt.copy_data), the same as grunt.copy_doc. */
  async function handleDuplicate() {
    if (!params.id) return
    let clone: Record<string, unknown>
    try {
      clone = await params.getCopy(params.doctype, params.id)
    } catch {
      params.toast.error(t('Could not duplicate the document'))
      return
    }
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
