import { nextTick, ref, watch } from 'vue'
import { useEventListener } from '@vueuse/core'

/**
 * Full-screen editing. Escape leaves it - unless a menu / popover is open
 * (reka-ui closes that first) - and never reaches the form's
 * "Escape = back to list" shortcut.
 */
export function useFullscreen(focus: () => void) {
  const fullscreen = ref(false)

  watch(fullscreen, () => nextTick(focus))

  useEventListener(window, 'keydown', (e: KeyboardEvent) => {
    if (!fullscreen.value || e.key !== 'Escape') return
    if (document.querySelector('[data-dismissable-layer]')) return
    e.stopPropagation()
    fullscreen.value = false
  }, { capture: true })

  return fullscreen
}
