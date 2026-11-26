import { describe, it, expect, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/core/api/docs', () => ({ docsApi: { get } }))

import { useDocument } from '../useDocument'

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let api!: ReturnType<typeof useDocument>
  mount(defineComponent({ setup() { api = useDocument('Case', 'C-1'); return () => h('div') } }), {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  return { api: () => api, queryClient }
}

describe('useDocument - refetched copy', () => {
  it('replaces a clean form', async () => {
    get.mockResolvedValueOnce({ id: 'C-1', title: 'A' })
    const { api, queryClient } = setup()
    await flushPromises()
    get.mockResolvedValueOnce({ id: 'C-1', title: 'B' })
    await queryClient.invalidateQueries({ queryKey: ['document', 'Case', 'C-1'] })
    await flushPromises()
    expect(api().form.value.title).toBe('B')
    expect(api().isDirty.value).toBe(false)
  })

  it('keeps edits made while the request was in flight', async () => {
    get.mockResolvedValueOnce({ id: 'C-1', title: 'A' })
    const { api, queryClient } = setup()
    await flushPromises()
    let resolve!: (v: unknown) => void
    get.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    const refetch = queryClient.invalidateQueries({ queryKey: ['document', 'Case', 'C-1'] })
    api().form.value = { ...api().form.value, title: 'my edit' }
    await nextTick()
    resolve({ id: 'C-1', title: 'B' })
    await refetch
    await flushPromises()
    expect(api().form.value.title).toBe('my edit')
    expect(api().isDirty.value).toBe(true)
  })
})
