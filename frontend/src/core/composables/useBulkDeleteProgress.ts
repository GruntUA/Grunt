import { onUnmounted, ref, type Ref } from 'vue'
import type { QueryClient } from '@tanstack/vue-query'
import { docsApi, filtersToRaw } from '@/core/api/docs'
import type { ActiveFilter } from '@/types'

interface UseBulkDeleteProgressParams {
  doctype: string
  metaTotal: Ref<number>
  selectedIds: Ref<string[]>
  allSelected: Ref<boolean>
  activeFilters: Ref<ActiveFilter[]>
  debouncedSearch: Ref<string>
  clearSelection: () => void
  queryClient: QueryClient
  onUserEvent: (event: string, handler: (d: Record<string, unknown>) => void) => void
  offUserEvent: (event: string, handler: (d: Record<string, unknown>) => void) => void
}

export function useBulkDeleteProgress(params: UseBulkDeleteProgressParams) {
  const deleteProgress = ref({ active: false, total: 0, done: 0, errors: 0 })

  let deleteProgressHandler: ((d: Record<string, unknown>) => void) | null = null
  let deleteDoneHandler: ((d: Record<string, unknown>) => void) | null = null

  onUnmounted(() => {
    if (deleteProgressHandler) params.offUserEvent('bulk_delete_progress', deleteProgressHandler)
    if (deleteDoneHandler) params.offUserEvent('bulk_delete_done', deleteDoneHandler)
  })

  async function bulkDelete() {
    const ids = params.allSelected.value ? [] : params.selectedIds.value
    if (!params.allSelected.value && !ids.length) return

    const total = params.allSelected.value ? params.metaTotal.value : ids.length
    deleteProgress.value = { active: true, total, done: 0, errors: 0 }

    function onProgress(data: Record<string, unknown>) {
      deleteProgress.value.done = (data.done as number) ?? deleteProgress.value.done
      deleteProgress.value.errors = (data.errors as number) ?? deleteProgress.value.errors
    }

    function onDone() {
      params.offUserEvent('bulk_delete_progress', onProgress)
      params.offUserEvent('bulk_delete_done', onDone)
      deleteProgressHandler = null
      deleteDoneHandler = null
      deleteProgress.value.active = false
      params.clearSelection()
      params.queryClient.invalidateQueries({ queryKey: ['documents', params.doctype] })
    }

    deleteProgressHandler = onProgress
    deleteDoneHandler = onDone
    params.onUserEvent('bulk_delete_progress', onProgress)
    params.onUserEvent('bulk_delete_done', onDone)

    try {
      if (params.allSelected.value) {
        await docsApi.bulkDelete(params.doctype, [], {
          deleteAll: true,
          rawFilters: filtersToRaw(params.activeFilters.value),
          search: params.debouncedSearch.value || undefined,
        })
      } else {
        await docsApi.bulkDelete(params.doctype, ids)
      }
    } catch {
      params.offUserEvent('bulk_delete_progress', onProgress)
      params.offUserEvent('bulk_delete_done', onDone)
      deleteProgressHandler = null
      deleteDoneHandler = null
      deleteProgress.value.active = false
    }
  }

  return {
    deleteProgress,
    bulkDelete,
  }
}
