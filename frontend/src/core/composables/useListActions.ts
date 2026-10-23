import type { QueryClient } from '@tanstack/vue-query'
import type { Ref } from 'vue'
import type { ActiveFilter } from '@/types'
import { docsApi } from '@/core/api/docs'

/** «Select all N» loads at most this many ids - narrow the filter for more. */
export const SELECT_ALL_LIMIT = 10000

interface UseListActionsOptions {
  doctype: string
  selectedIds: Ref<string[]>
  debouncedSearch: Ref<string>
  activeFilters: Ref<ActiveFilter[]>
  /** Quick-filter values in backend format - part of what «all matching» means. */
  quickFilters?: Ref<Record<string, string>>
  clearSelection: () => void
  queryClient: QueryClient
}

export function useListActions(options: UseListActionsOptions) {
  /** Ids of every document the list matches (filters, quick filters, search), up to SELECT_ALL_LIMIT. */
  async function loadAllIds(): Promise<{ ids: string[]; total: number }> {
    const res = await docsApi.list(options.doctype, {
      page: 1,
      per_page: SELECT_ALL_LIMIT,
      fields: 'name',
      search: options.debouncedSearch.value || undefined,
      filters: options.activeFilters.value,
      quickFilters: options.quickFilters?.value,
    })
    const ids = res.data.map((row) => String(row.name))
    return { ids, total: res.meta?.total ?? ids.length }
  }

  async function bulkUpdate(field: string, value: unknown) {
    const ids = options.selectedIds.value
    if (ids.length) {
      await docsApi.bulkUpdate(options.doctype, ids, field, value)
    }

    options.clearSelection()
    options.queryClient.invalidateQueries({ queryKey: ['documents', options.doctype] })
  }

  async function inlineUpdate(rowId: string, field: string, value: string) {
    await docsApi.update(options.doctype, rowId, { [field]: value })
    options.queryClient.invalidateQueries({ queryKey: ['documents', options.doctype] })
  }

  return {
    loadAllIds,
    bulkUpdate,
    inlineUpdate,
  }
}
