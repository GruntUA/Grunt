import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import type { QueryClient } from '@tanstack/vue-query'
import type { ActiveFilter } from '@/types'
import { SELECT_ALL_LIMIT, useListActions } from '../useListActions'
import { docsApi } from '@/core/api/docs'

vi.mock('@/core/api/docs', () => ({
  docsApi: {
    list: vi.fn(),
    bulkUpdate: vi.fn(),
    update: vi.fn(),
  },
}))

describe('useListActions', () => {
  const clearSelection = vi.fn()
  const invalidateQueries = vi.fn()
  const queryClient = { invalidateQueries } as unknown as QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('bulk updates selected ids directly', async () => {
    const { bulkUpdate } = useListActions({
      doctype: 'Task',
      selectedIds: ref(['a', 'b']),
      debouncedSearch: ref(''),
      activeFilters: ref([]),
      clearSelection,
      queryClient,
    })

    await bulkUpdate('status', 'Open')

    expect(docsApi.bulkUpdate).toHaveBeenCalledWith('Task', ['a', 'b'], 'status', 'Open')
    expect(clearSelection).toHaveBeenCalled()
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['documents', 'Task'] })
  })

  it('loads every matching id with filters, quick filters and search', async () => {
    const activeFilters = ref<ActiveFilter[]>([
      { fieldname: 'status', label: 'Status', op: '=', value: 'Open' },
    ])
    vi.mocked(docsApi.list).mockResolvedValue({
      data: [{ name: '1' }, { name: '2' }],
      meta: { total: 12000 },
    } as never)

    const { loadAllIds } = useListActions({
      doctype: 'Task',
      selectedIds: ref([]),
      debouncedSearch: ref('john'),
      activeFilters,
      quickFilters: ref({ priority__eq: 'High' }),
      clearSelection,
      queryClient,
    })

    const result = await loadAllIds()

    expect(docsApi.list).toHaveBeenCalledWith('Task', expect.objectContaining({
      per_page: SELECT_ALL_LIMIT,
      fields: 'name',
      search: 'john',
      filters: activeFilters.value,
      quickFilters: { priority__eq: 'High' },
    }))
    expect(result).toEqual({ ids: ['1', '2'], total: 12000 })
  })

  it('updates a single row inline', async () => {
    const { inlineUpdate } = useListActions({
      doctype: 'Task',
      selectedIds: ref([]),
      debouncedSearch: ref(''),
      activeFilters: ref([]),
      clearSelection,
      queryClient,
    })

    await inlineUpdate('row-1', 'status', 'Closed')

    expect(docsApi.update).toHaveBeenCalledWith('Task', 'row-1', { status: 'Closed' })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['documents', 'Task'] })
  })
})