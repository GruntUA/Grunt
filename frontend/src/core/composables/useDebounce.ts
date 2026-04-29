import { onUnmounted, ref, watch, isRef, type Ref } from 'vue'

export function useDebounce<T>(source: Ref<T>, delayMs: number | Ref<number>): Ref<T> {
  const debounced = ref(source.value) as Ref<T>
  let timer: ReturnType<typeof setTimeout> | null = null

  watch(source, (value) => {
    if (timer) clearTimeout(timer)
    const delay = isRef(delayMs) ? delayMs.value : delayMs
    timer = setTimeout(() => {
      debounced.value = value
      timer = null
    }, delay)
  })

  onUnmounted(() => {
    if (timer) clearTimeout(timer)
  })

  return debounced
}
