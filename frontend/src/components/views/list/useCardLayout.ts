import { useMediaQuery } from '@vueuse/core'

/** Phone-width screens show list rows as cards instead of a table (same breakpoint as the app sidebar). */
export function useCardLayout() {
  return useMediaQuery('(max-width: 767px)')
}
