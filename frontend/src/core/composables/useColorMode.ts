import { ref, watchEffect } from 'vue'

// Singleton state - shared across all components
const stored = localStorage.getItem('grunt_theme')
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
const isDark = ref(stored === 'dark' || (!stored && prefersDark))

// Apply immediately
document.documentElement.classList.toggle('dark', isDark.value)

watchEffect(() => {
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('grunt_theme', isDark.value ? 'dark' : 'light')
})

export function useColorMode() {
  return {
    isDark,
    toggle() { isDark.value = !isDark.value },
  }
}
