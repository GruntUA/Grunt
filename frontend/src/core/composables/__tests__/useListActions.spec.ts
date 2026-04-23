import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import type { QueryClient } from '@tanstack/vue-query'
import type { ActiveFilter } from '@/types'
import { useListActions } from '../useListActions'
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
      allSelected: ref(false),
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

  it('loads ids first when allSelected is active', async () => {
    const activeFilters = ref<ActiveFilter[]>([
      {
        fieldname: 'status',
        label: 'Status',
        op: '=',
        value: 'Open',
      },
    ])

    vi.mocked(docsApi.list).mockResolvedValue({
      data: [{ id: 1 }, { id: 2 }],
      meta: {},
    } as never)

    const { bulkUpdate } = useListActions({
      doctype: 'Task',
      selectedIds: ref([]),
      allSelected: ref(true),
      debouncedSearch: ref('john'),
      activeFilters,
      clearSelection,
      queryClient,
    })

    await bulkUpdate('priority', 'High')

    expect(docsApi.list).toHaveBeenCalled()
    expect(docsApi.bulkUpdate).toHaveBeenCalledWith('Task', ['1', '2'], 'priority', 'High')
  })

  it('updates a single row inline', async () => {
    const { inlineUpdate } = useListActions({
      doctype: 'Task',
      selectedIds: ref([]),
      allSelected: ref(false),
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