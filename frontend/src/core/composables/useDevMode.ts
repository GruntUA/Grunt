import { ref, onMounted, onUnmounted } from 'vue'

const altPressed = ref(false)

let listeners = 0

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Alt') altPressed.value = true
}

function onKeyUp(e: KeyboardEvent) {
  if (e.key === 'Alt') altPressed.value = false
}

function onBlur() {
  altPressed.value = false
}

export function useDevMode() {
  const isDev = import.meta.env.DEV

  onMounted(() => {
    if (!isDev) return
    if (listeners++ === 0) {
      window.addEventListener('keydown', onKeyDown)
      window.addEventListener('keyup', onKeyUp)
      window.addEventListener('blur', onBlur)
    }
  })

  onUnmounted(() => {
    if (!isDev) return
    if (--listeners === 0) {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', onBlur)
    }
  })

  return { isDev, altPressed }
}
