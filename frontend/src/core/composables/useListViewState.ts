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
  perPage: number
}

const PER_PAGE_OPTIONS = [20, 50, 100] as const
const DEFAULT_PER_PAGE = 20

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
  const perPage = ref<number>(
    PER_PAGE_OPTIONS.includes(saved.perPage as typeof PER_PAGE_OPTIONS[number])
      ? (saved.perPage as number)
      : DEFAULT_PER_PAGE,
  )

  watch(
    [viewMode, sortKey, sortOrder, groupBy, activeFilters, quickFilterValues, search, perPage],
    () => {
      saveState(doctype, {
        viewMode: viewMode.value,
        sortKey: sortKey.value,
        sortOrder: sortOrder.value,
        groupBy: groupBy.value,
        activeFilters: activeFilters.value,
        quickFilterValues: quickFilterValues.value,
        search: search.value,
        perPage: perPage.value,
      })
    },
    { deep: true },
  )

  return { viewMode, sortKey, sortOrder, groupBy, activeFilters, quickFilterValues, search, perPage }
}

export { PER_PAGE_OPTIONS }
