import { defineStore } from 'pinia'
import { ref } from 'vue'
import { metaApi } from '@/core/api/meta'
import type { DocType, DocTypeSummary } from '@/types'

export const useDocTypeStore = defineStore('doctype', () => {
  const doctypes = ref<DocTypeSummary[]>([])
  const cache = ref<Map<string, DocType>>(new Map())
  const loading = ref(false)

  async function loadAll() {
    loading.value = true
    try {
      doctypes.value = await metaApi.list()
    } finally {
      loading.value = false
    }
  }

  async function get(name: string): Promise<DocType> {
    if (cache.value.has(name)) return cache.value.get(name)!
    const dt = await metaApi.get(name)
    cache.value.set(name, dt)
    return dt
  }

  function invalidate(name: string) {
    cache.value.delete(name)
  }

  /** Drop every cached schema — e.g. after a UI language switch. */
  function invalidateAll() {
    cache.value.clear()
  }

  return { doctypes, loading, cache, loadAll, get, invalidate, invalidateAll }
})
