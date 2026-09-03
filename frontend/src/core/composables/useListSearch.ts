import { ref, watch } from 'vue'
import type { Ref } from 'vue'
import { useDebounce } from '@/core/composables/useDebounce'

export function useListSearch(page: Ref<number>, searchRef?: Ref<string>, delayMs = 400) {
  const inlineSearch = searchRef ?? ref('')
  const debouncedSearch = useDebounce(inlineSearch, delayMs)

  watch(debouncedSearch, () => {
    page.value = 1
  })

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
