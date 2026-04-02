import { ref, onMounted, onUnmounted } from 'vue'

const isOpen = ref(false)

export function useCommandPalette() {
  function open() { isOpen.value = true }
  function close() { isOpen.value = false }
  function toggle() { isOpen.value = !isOpen.value }

  return { isOpen, open, close, toggle }
}

/**
 * Register the global Ctrl+K / Cmd+K shortcut.
 * Call once at the application root (App.vue).
 */
export function useCommandPaletteShortcut() {
  const { toggle } = useCommandPalette()

  function onKeydown(e: KeyboardEvent) {
    const isMac = navigator.platform.toUpperCase().includes('MAC')
    const modifier = isMac ? e.metaKey : e.ctrlKey
    if (modifier && e.key === 'k') {
      e.preventDefault()
      toggle()
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeydown))
  onUnmounted(() => window.removeEventListener('keydown', onKeydown))
}
