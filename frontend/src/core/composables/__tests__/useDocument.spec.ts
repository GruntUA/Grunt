import { describe, it, expect, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/core/api/docs', () => ({ docsApi: { get } }))
vi.mock('@/core/composables/useFormDraft', () => ({ clearFormDraft: vi.fn() }))

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

  it('fills the form with the first copy even if the form was written before it', async () => {
    let resolve!: (v: unknown) => void
    get.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    const { api } = setup()
    // e.g. fetch_from clearing its field while the document is still loading
    api().form.value = { ...api().form.value, type_name: null }
    await nextTick()
    resolve({ id: 'C-1', title: 'A' })
    await flushPromises()
    expect(api().form.value.title).toBe('A')
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

  it('reload() replaces unsaved edits (frm.reload, «Оновити»)', async () => {
    get.mockResolvedValueOnce({ id: 'C-1', title: 'A' })
    const { api } = setup()
    await flushPromises()
    api().form.value = { ...api().form.value, title: 'my edit' }
    await nextTick()
    get.mockResolvedValueOnce({ id: 'C-1', title: 'B' })
    await api().reload()
    expect(api().form.value.title).toBe('B')
    expect(api().isDirty.value).toBe(false)
  })

  it('reload() keeps the edits and throws when the request fails', async () => {
    get.mockResolvedValueOnce({ id: 'C-1', title: 'A' })
    const { api } = setup()
    await flushPromises()
    api().form.value = { ...api().form.value, title: 'my edit' }
    await nextTick()
    // The query still holds copy A after the failure - not the stored document.
    get.mockRejectedValueOnce(new Error('offline'))
    await expect(api().reload()).rejects.toThrow('offline')
    expect(api().form.value.title).toBe('my edit')
    expect(api().isDirty.value).toBe(true)
  })
})
