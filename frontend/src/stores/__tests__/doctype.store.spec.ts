import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDocTypeStore } from '@/stores/doctype'
import type { DocType, DocTypeSummary } from '@/types'

// ── Mocks ──────────────────────────────────────────────────────────────────

const { mockList, mockGet } = vi.hoisted(() => ({
  mockList: vi.fn(),
  mockGet: vi.fn(),
}))

vi.mock('@/core/api/meta', () => ({
  metaApi: {
    list: mockList,
    get: mockGet,
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    sync: vi.fn(),
  },
}))

// ── Fixtures ───────────────────────────────────────────────────────────────

const fakeSummary: DocTypeSummary = { name: 'Order', label: 'Order', module: 'crm', is_system: false }

const fakeDocType: DocType = {
  name: 'Order',
  label: 'Order',
  module: 'crm',
  fields: [
    { fieldname: 'title', label: 'Title', fieldtype: 'Text', required: true },
    { fieldname: 'status', label: 'Status', fieldtype: 'Select', options: 'Open\nClosed' },
  ],
  permissions: [],
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('useDocTypeStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockList.mockReset()
    mockGet.mockReset()
  })

  describe('loadAll', () => {
    it('populates doctypes list', async () => {
      mockList.mockResolvedValueOnce([fakeSummary])
      const store = useDocTypeStore()
      await store.loadAll()
      expect(store.doctypes).toHaveLength(1)
      expect(store.doctypes[0].name).toBe('Order')
    })

    it('sets loading flag during fetch', async () => {
      let resolveList!: (v: DocTypeSummary[]) => void
      mockList.mockReturnValueOnce(new Promise(r => { resolveList = r }))
      const store = useDocTypeStore()
      const promise = store.loadAll()
      expect(store.loading).toBe(true)
      resolveList([fakeSummary])
      await promise
      expect(store.loading).toBe(false)
    })

    it('clears loading flag on error', async () => {
      mockList.mockRejectedValueOnce(new Error('Network'))
      const store = useDocTypeStore()
      await expect(store.loadAll()).rejects.toThrow()
      expect(store.loading).toBe(false)
    })
  })

  describe('get', () => {
    it('fetches a doctype by name', async () => {
      mockGet.mockResolvedValueOnce(fakeDocType)
      const store = useDocTypeStore()
      const dt = await store.get('Order')
      expect(dt.name).toBe('Order')
      expect(dt.fields).toHaveLength(2)
    })

    it('caches the result — second call does not re-fetch', async () => {
      mockGet.mockResolvedValueOnce(fakeDocType)
      const store = useDocTypeStore()
      await store.get('Order')
      await store.get('Order')
      expect(mockGet).toHaveBeenCalledOnce()
    })

    it('re-fetches after invalidate', async () => {
      mockGet.mockResolvedValue(fakeDocType)
      const store = useDocTypeStore()
      await store.get('Order')
      store.invalidate('Order')
      await store.get('Order')
      expect(mockGet).toHaveBeenCalledTimes(2)
    })
  })

  describe('invalidate', () => {
    it('removes the doctype from cache', async () => {
      mockGet.mockResolvedValue(fakeDocType)
      const store = useDocTypeStore()
      await store.get('Order')
      store.invalidate('Order')
      // After invalidation, get() should fetch again
      await store.get('Order')
      expect(mockGet).toHaveBeenCalledTimes(2)
    })

    it('is a no-op for unknown names', () => {
      const store = useDocTypeStore()
      expect(() => store.invalidate('NonExistent')).not.toThrow()
    })
  })
})
