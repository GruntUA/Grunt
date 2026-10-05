import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AppPage } from '@/core/api/pages'
import { fetchPages } from '@/core/api/pages'

export const usePageStore = defineStore('pages', () => {
  const pages = ref<AppPage[]>([])
  const loaded = ref(false)

  async function loadAll() {
    if (loaded.value) return
    try {
      pages.value = await fetchPages()
      loaded.value = true
    } catch {
      // ignore - pages are optional
    }
  }

  return { pages, loaded, loadAll }
})
