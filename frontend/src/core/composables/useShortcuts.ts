import { useEventListener } from '@vueuse/core'

import { matchesShortcut } from '@/core/shortcuts'

interface ShortcutOptions {
  /** Prevent default browser behavior */
  preventDefault?: boolean
  /** Trigger even if the user is typing inside an input/textarea */
  allowInInput?: boolean
}

/**
 * Checks if the currently focused element is an input, textarea, or contenteditable.
 */
export function isUserTyping(): boolean {
  if (typeof document === 'undefined') return false
  const active = document.activeElement as HTMLElement | null
  if (!active) return false
  const tagName = active.tagName.toLowerCase()
  return tagName === 'input' || tagName === 'textarea' || tagName === 'select' || active.isContentEditable
}

/**
 * Registers a keyboard shortcut for the lifetime of the component.
 *
 * @param keys One or more shortcuts in core/shortcuts.ts notation ('Mod+S', 'Escape')
 * @param handler Callback to execute when pressed
 */
export function useShortcut(
  keys: string | string[],
  handler: (e: KeyboardEvent) => void,
  options: ShortcutOptions = {},
) {
  const { preventDefault = false, allowInInput = false } = options
  const patterns = Array.isArray(keys) ? keys : [keys]

  useEventListener('keydown', (e: KeyboardEvent) => {
    if (!patterns.some((p) => matchesShortcut(e, p))) return
    if (!allowInInput && isUserTyping()) return
    if (preventDefault) e.preventDefault()
    handler(e)
  })
}
