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

  /** Subscribe to WebSocket progress events and track progress state. */
  function _subscribeProgress(total: number) {
    deleteProgress.value = { active: true, total, done: 0, errors: 0 }

    function onProgress(data: Record<string, unknown>) {
      deleteProgress.value.done = (data.done as number) ?? deleteProgress.value.done
      deleteProgress.value.total = (data.total as number) ?? deleteProgress.value.total
      deleteProgress.value.errors = (data.errors as number) ?? deleteProgress.value.errors
    }

    function onDone(data: Record<string, unknown>) {
      params.offUserEvent('bulk_delete_progress', onProgress)
      params.offUserEvent('bulk_delete_done', onDone)
      deleteProgressHandler = null
      deleteDoneHandler = null
      // Show final count from server
      if (data.deleted != null) {
        deleteProgress.value.done = data.deleted as number
        deleteProgress.value.total = data.deleted as number
      }
      deleteProgress.value.active = false
      params.clearSelection()
      params.queryClient.invalidateQueries({ queryKey: ['documents', params.doctype] })
    }

    deleteProgressHandler = onProgress
    deleteDoneHandler = onDone
    params.onUserEvent('bulk_delete_progress', onProgress)
    params.onUserEvent('bulk_delete_done', onDone)

    return () => {
      params.offUserEvent('bulk_delete_progress', onProgress)
      params.offUserEvent('bulk_delete_done', onDone)
      deleteProgressHandler = null
      deleteDoneHandler = null
      deleteProgress.value.active = false
    }
  }

  /** Normal bulk delete — respects lifecycle hooks, streams batch progress. */
  async function bulkDelete(replaceWith?: string) {
    const ids = params.allSelected.value ? [] : params.selectedIds.value
    if (!params.allSelected.value && !ids.length) return

    const total = params.allSelected.value ? params.metaTotal.value : ids.length
    const unsubscribe = _subscribeProgress(total)

    try {
      if (params.allSelected.value) {
        await docsApi.bulkDelete(params.doctype, [], {
          deleteAll: true,
          rawFilters: filtersToRaw(params.activeFilters.value),
          search: params.debouncedSearch.value || undefined,
        })
      } else {
        await docsApi.bulkDelete(params.doctype, ids, { replaceWith })
      }
    } catch {
      unsubscribe()
    }
  }

  /** Fast delete — direct SQL, no hooks, superadmin only. Near-instant for large datasets. */
  async function bulkFastDelete() {
    const total = params.metaTotal.value
    const unsubscribe = _subscribeProgress(total)

    try {
      await docsApi.bulkDelete(params.doctype, [], {
        deleteAll: true,
        rawFilters: filtersToRaw(params.activeFilters.value),
        search: params.debouncedSearch.value || undefined,
        fast: true,
      })
    } catch {
      unsubscribe()
    }
  }

  return {
    deleteProgress,
    bulkDelete,
    bulkFastDelete,
  }
}
