import { ref, watch } from 'vue'
import type { ActiveFilter } from '@/types'

interface ListViewState {
  viewMode: string
  sortKey: string
  sortOrder: 'asc' | 'desc'
  groupBy: string | null
  activeFilters: ActiveFilter[]
  quickFilterValues: Record<string, string>
  search: string
}

function storageKey(doctype: string) {
  return `grunt_list_state_${doctype}`
}

function loadState(doctype: string): Partial<ListViewState> {
  try {
    const raw = localStorage.getItem(storageKey(doctype))
    return raw ? (JSON.parse(raw) as Partial<ListViewState>) : {}
  } catch {
    return {}
  }
}

function saveState(doctype: string, state: ListViewState) {
  localStorage.setItem(storageKey(doctype), JSON.stringify(state))
}

export function useListViewState(doctype: string) {
  const saved = loadState(doctype)

  const viewMode = ref<string>(saved.viewMode ?? 'list')
  const sortKey = ref<string>(saved.sortKey ?? '')
  const sortOrder = ref<'asc' | 'desc'>(saved.sortOrder ?? 'asc')
  const groupBy = ref<string | null>(saved.groupBy ?? null)
  const activeFilters = ref<ActiveFilter[]>(saved.activeFilters ?? [])
  const quickFilterValues = ref<Record<string, string>>(saved.quickFilterValues ?? {})
  const search = ref<string>(saved.search ?? '')

  watch(
    [viewMode, sortKey, sortOrder, groupBy, activeFilters, quickFilterValues, search],
    () => {
      saveState(doctype, {
        viewMode: viewMode.value,
        sortKey: sortKey.value,
        sortOrder: sortOrder.value,
        groupBy: groupBy.value,
        activeFilters: activeFilters.value,
        quickFilterValues: quickFilterValues.value,
        search: search.value,
      })
    },
    { deep: true },
  )

  return { viewMode, sortKey, sortOrder, groupBy, activeFilters, quickFilterValues, search }
}
