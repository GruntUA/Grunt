import { ref, watch } from 'vue'
import type { ActiveFilter } from '@/types'

type ViewMode = 'list' | 'kanban' | 'calendar' | 'tree' | 'gallery' | 'map'

interface ListViewState {
  viewMode: ViewMode
  sortKey: string
  sortOrder: 'asc' | 'desc'
  groupBy: string | null
  activeFilters: ActiveFilter[]
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

  const viewMode = ref<ViewMode>(saved.viewMode ?? 'list')
  const sortKey = ref<string>(saved.sortKey ?? '')
  const sortOrder = ref<'asc' | 'desc'>(saved.sortOrder ?? 'asc')
  const groupBy = ref<string | null>(saved.groupBy ?? null)
  const activeFilters = ref<ActiveFilter[]>(saved.activeFilters ?? [])

  watch(
    [viewMode, sortKey, sortOrder, groupBy, activeFilters],
    () => {
      saveState(doctype, {
        viewMode: viewMode.value,
        sortKey: sortKey.value,
        sortOrder: sortOrder.value,
        groupBy: groupBy.value,
        activeFilters: activeFilters.value,
      })
    },
    { deep: true },
  )

  return { viewMode, sortKey, sortOrder, groupBy, activeFilters }
}
