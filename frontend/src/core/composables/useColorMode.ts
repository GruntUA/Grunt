import { ref, computed, watchEffect } from 'vue'

export type Theme = 'light' | 'dark' | 'system'

// ── Singleton state ──────────────────────────────────────────────────────

const systemDark = window.matchMedia('(prefers-color-scheme: dark)')
const stored = localStorage.getItem('grunt_theme') as Theme | null
const _theme = ref<Theme>(stored ?? 'system')
const _systemDark = ref(systemDark.matches)

// Track OS-level preference changes
systemDark.addEventListener('change', (e) => { _systemDark.value = e.matches })

const isDark = computed(() =>
  _theme.value === 'system' ? _systemDark.value : _theme.value === 'dark'
)

watchEffect(() => {
  document.documentElement.classList.toggle('dark', isDark.value)
})

// ── Public API ───────────────────────────────────────────────────────────

export function useColorMode() {
  function setTheme(theme: Theme) {
    _theme.value = theme
    localStorage.setItem('grunt_theme', theme)
  }

  return { isDark, currentTheme: _theme, setTheme }
}
