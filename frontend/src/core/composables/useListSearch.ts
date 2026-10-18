import { ref } from 'vue'
import type { Ref } from 'vue'
import { useDebounce } from '@/core/composables/useDebounce'

export const SEARCH_DEBOUNCE_MS = 400

export function useListSearch(page: Ref<number>, searchRef?: Ref<string>, delayMs = SEARCH_DEBOUNCE_MS) {
  const inlineSearch = searchRef ?? ref('')
  const debouncedSearch = useDebounce(inlineSearch, delayMs)

  function resetSearch() {
    inlineSearch.value = ''
    page.value = 1
  }

  return {
    inlineSearch,
    debouncedSearch,
    resetSearch,
  }
}
