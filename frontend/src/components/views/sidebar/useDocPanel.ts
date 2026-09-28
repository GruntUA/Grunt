/**
 * Show/hide + width state for the document detail sidebar.
 *
 * Mirrors the shape of shadcn's `useSidebar` (state / open / toggle / isMobile),
 * but is a standalone module — the app-shell `<SidebarProvider>` is a singleton
 * for the *left* nav (shared cookie + Cmd/Ctrl+B) and must not be reused here.
 *
 * Preference is persisted per-viewer in localStorage. Desktop collapses the
 * panel to zero width; mobile opens it as an off-canvas sheet.
 */
import { computed, ref, watch } from 'vue'
import { useEventListener, useMediaQuery } from '@vueuse/core'
import { matchesShortcut } from '@/core/shortcuts'

const OPEN_KEY = 'doc_panel_open'
const WIDTH_KEY = 'doc_panel_width'
const SHORTCUT = 'Mod+]' // the left nav owns Mod+B
const DEFAULT_WIDTH = 300
const MIN_WIDTH = 260
const MAX_WIDTH = 520

function read(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

function persist(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* private mode / blocked storage — ignore */
  }
}

// ── module-level state so the header toggle and the panel share one source ────
const open = ref(read(OPEN_KEY, 'true') !== 'false')
const width = ref(clampWidth(Number(read(WIDTH_KEY, String(DEFAULT_WIDTH)))))

function clampWidth(px: number): number {
  if (!Number.isFinite(px)) return DEFAULT_WIDTH
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(px)))
}

watch(open, (v) => persist(OPEN_KEY, String(v)))
watch(width, (v) => persist(WIDTH_KEY, String(v)))

let shortcutBound = false

export function useDocPanel() {
  const isMobile = useMediaQuery('(max-width: 1023px)')
  const openMobile = ref(false)

  function toggle(): void {
    if (isMobile.value) openMobile.value = !openMobile.value
    else open.value = !open.value
  }

  function setWidth(px: number): void {
    width.value = clampWidth(px)
  }

  // Bind the keyboard shortcut once, from whichever consumer mounts first.
  if (!shortcutBound) {
    shortcutBound = true
    useEventListener('keydown', (e: KeyboardEvent) => {
      if (matchesShortcut(e, SHORTCUT)) {
        e.preventDefault()
        toggle()
      }
    })
  }

  const state = computed(() => (open.value ? 'expanded' : 'collapsed'))

  return { open, openMobile, isMobile, state, width, toggle, setWidth, MIN_WIDTH, MAX_WIDTH }
}
