import { onKeyStroke } from '@vueuse/core'

type Key = string | string[]

interface ShortcutOptions {
  /** Prevent default browser behavior */
  preventDefault?: boolean
  /** Trigger even if the user is typing inside an input/textarea */
  allowInInput?: boolean
  /** Exact match modifier keys (Ctrl/Cmd) */
  exact?: boolean
}

/**
 * Checks if the currently focused element is an input, textarea, or contenteditable.
 */
export function isUserTyping(): boolean {
  if (typeof document === 'undefined') return false
  const active = document.activeElement as HTMLElement
  if (!active) return false
  
  const tagName = active.tagName.toLowerCase()
  if (tagName === 'input' || tagName === 'textarea' || tagName === 'select') {
    return true
  }
  if (active.isContentEditable) {
    return true
  }
  return false
}

/**
 * Registers a keyboard shortcut.
 * 
 * @param keys The key or array of keys ('Ctrl+S', 'Escape', 'Enter')
 * @param handler Callback to execute when pressed
 * @param options Options like preventing default or allowing in inputs
 */
export function useShortcut(
  keys: Key,
  handler: (e: KeyboardEvent) => void,
  options: ShortcutOptions = {}
) {
  const {
    preventDefault = false,
    allowInInput = false,
  } = options

  // Because typical shortcut keys in VueUse onKeyStroke don't handle 'Ctrl+S' automatically
  // with modifier parsing on a global handler easily if we want to be exact,
  // we'll explicitly parse basic modifiers from the string if passed, 
  // though onKeyStroke handles basic keys directly via KeyboardEvent.key.

  // Normalizing for onKeyStroke which expects valid KeyboardEvent.key strings.
  // VueUse onKeyStroke can accept array of keys.
  
  // Custom modifier logic wrapper
  const triggerHandler = (e: KeyboardEvent) => {
    // If the user is typing in an input, ignore unless allowed
    if (!allowInInput && isUserTyping()) {
      return
    }

    if (preventDefault) {
      e.preventDefault()
    }
    
    // Stop propagation so it doesn't trigger parent shortcuts
    e.stopPropagation()

    handler(e)
  }

  // Define keys for onKeyStroke. For complex things like Ctrl+S, we just use keydown
  // because VueUse's onKeyStroke expects 's'. Let's parse modifier combinations natively.
  onKeyStroke(
    (e) => {
      // Check if it matches any pattern
      const patterns = Array.isArray(keys) ? keys : [keys]
      
      for (const pattern of patterns) {
        const parts = pattern.toLowerCase().split('+')
        const key = parts[parts.length - 1]
        
        const needsCtrlOrCmd = parts.includes('ctrl') || parts.includes('cmd')
        const needsShift = parts.includes('shift')
        const needsAlt = parts.includes('alt')

        // Check modifiers
        const hasCtrlOrCmd = e.ctrlKey || e.metaKey
        if (needsCtrlOrCmd !== hasCtrlOrCmd) continue
        if (needsShift !== e.shiftKey) continue
        if (needsAlt !== e.altKey) continue

        // e.key format check. For letters, case varies if shift is held. 
        // We match case-insensitively for alphabet letters.
        if (e.key.toLowerCase() === key || e.code.toLowerCase() === `key${key}`) {
           return true
        }
      }
      return false
    },
    triggerHandler,
    { eventName: 'keydown' }
  )
}
