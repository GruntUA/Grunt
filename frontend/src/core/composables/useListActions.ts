import type { QueryClient } from '@tanstack/vue-query'
import type { Ref } from 'vue'
import type { ActiveFilter } from '@/types'
import { docsApi } from '@/core/api/docs'

interface UseListActionsOptions {
  doctype: string
  selectedIds: Ref<string[]>
  allSelected: Ref<boolean>
  debouncedSearch: Ref<string>
  activeFilters: Ref<ActiveFilter[]>
  clearSelection: () => void
  queryClient: QueryClient
}

export function useListActions(options: UseListActionsOptions) {
  async function bulkUpdate(field: string, value: string) {
    const ids = options.allSelected.value
      ? (
          await docsApi.list(options.doctype, {
            page: 1,
            per_page: 10000,
            fields: 'name',
            search: options.debouncedSearch.value || undefined,
            filters: options.activeFilters.value,
          })
        ).data.map((row) => row.name)
      : options.selectedIds.value

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
    bulkUpdate,
    inlineUpdate,
  }
}