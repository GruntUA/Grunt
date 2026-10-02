import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import { useListRouteSync } from '../useListRouteSync'
import type { ActiveFilter, DocType } from '@/types'

describe('useListRouteSync', () => {
  const replace = vi.fn()

  function setup(query: Record<string, unknown> = {}) {
    const viewMode = ref('list')
    const groupBy = ref<string | null>(null)
    const sortKey = ref('')
    const sortOrder = ref<'asc' | 'desc'>('asc')
    const activeFilters = ref<ActiveFilter[]>([])
    const dt = ref<DocType | null>(null)
    const search = ref('')
    const debouncedSearch = ref('')
    replace.mockReset()

    const route = { query } as RouteLocationNormalizedLoaded
    const router = { replace } as unknown as Router

    const api = useListRouteSync({
      route,
      router,
      viewMode,
      groupBy,
      sortKey,
      sortOrder,
      activeFilters,
      search,
      debouncedSearch,
      validViews: ['list', 'kanban', 'calendar'],
      getDefaultView: () => 'list',
      dt,
    })

    return {
      ...api,
      viewMode,
      groupBy,
      sortKey,
      sortOrder,
      activeFilters,
      search,
      debouncedSearch,
      dt,
    }
  }

  beforeEach(() => {
    replace.mockReset()
  })

  it('applies route state from query', () => {
    const { applyRouteState, viewMode, groupBy, sortKey, sortOrder } = setup({
      view: 'kanban',
      groupBy: 'status',
      sort: 'name',
      order: 'desc',
    })

    applyRouteState()

    expect(viewMode.value).toBe('kanban')
    expect(groupBy.value).toBe('status')
    expect(sortKey.value).toBe('name')
    expect(sortOrder.value).toBe('desc')
  })

  it('falls back to default view for invalid mode', () => {
    const { applyRouteState, viewMode } = setup({ view: 'unknown' })
    viewMode.value = 'invalid'

    applyRouteState()

    expect(viewMode.value).toBe('list')
  })

  it('syncs view mode changes to route', async () => {
    const { viewMode } = setup()

    viewMode.value = 'kanban'
    await nextTick()

    expect(replace).toHaveBeenCalledWith({ query: { view: 'kanban' } })
  })

  it('removes view from route when switching to default', async () => {
    const { viewMode, applyRouteState } = setup({ view: 'kanban', foo: 'bar' })

    applyRouteState()
    await nextTick()
    replace.mockReset()

    viewMode.value = 'list'
    await nextTick()

    expect(replace).toHaveBeenLastCalledWith({ query: { foo: 'bar' } })
  })

  it('updates groupBy in route', () => {
    const { setGroupByInRoute } = setup({ foo: 'bar' })

    setGroupByInRoute('status')

    expect(replace).toHaveBeenCalledWith({ query: { foo: 'bar', groupBy: 'status' } })
  })

  it('applies sort and toggles order', () => {
    const { applySort, sortKey, sortOrder } = setup({ foo: 'bar' })
    sortKey.value = 'name'
    sortOrder.value = 'asc'

    applySort('name')

    expect(sortOrder.value).toBe('desc')
    expect(sortKey.value).toBe('name')
    expect(replace).toHaveBeenCalledWith({ query: { foo: 'bar', sort: 'name', order: 'desc' } })
  })

  it('applies search from q', () => {
    const { applyRouteState, search } = setup({ q: 'державні сайт' })

    applyRouteState()

    expect(search.value).toBe('державні сайт')
  })

  it('writes debounced search to q and drops it when cleared', async () => {
    const { debouncedSearch } = setup({ foo: 'bar' })

    debouncedSearch.value = '  сайт '
    await nextTick()
    expect(replace).toHaveBeenLastCalledWith({ query: { foo: 'bar', q: 'сайт' } })

    debouncedSearch.value = ''
    await nextTick()
    expect(replace).toHaveBeenLastCalledWith({ query: { foo: 'bar' } })
  })
})
