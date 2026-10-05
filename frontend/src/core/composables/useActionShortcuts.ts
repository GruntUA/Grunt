import { onBeforeUnmount, onMounted } from 'vue'

import type { ActionRegistry } from '@/core/actions'
import { matchesShortcut } from '@/core/shortcuts'

/**
 * Keyboard shortcuts declared by actions (`shortcut: 'Mod+S'`): a visible,
 * enabled action whose shortcut matches runs, and the browser default
 * (e.g. «Save page») is suppressed. Works while typing in a field.
 *
 * Listens in the capture phase, so a field that stops keydown propagation
 * (an editor, a combobox) doesn't swallow Ctrl+S.
 *
 * The focused field is blurred before the action runs and refocused after:
 * fields that commit on blur (a typed date) would otherwise be saved with
 * their previous value.
 */
export function useActionShortcuts(registry: ActionRegistry) {
  function onKeydown(event: KeyboardEvent) {
    if (event.defaultPrevented) return
    const action = registry.withShortcut().find((a) => a.shortcut && matchesShortcut(event, a.shortcut))
    if (!action) return
    event.preventDefault()
    // Held keys repeat: suppress «Save page» for every repeat, run once.
    if (!event.repeat) void runCommitted(action.run)
  }

  async function runCommitted(run: () => unknown) {
    const focused = document.activeElement
    const field = focused instanceof HTMLElement && focused !== document.body ? focused : null
    field?.blur()
    try {
      await run()
    } finally {
      if (field?.isConnected && document.activeElement === document.body) field.focus()
    }
  }
  onMounted(() => window.addEventListener('keydown', onKeydown, { capture: true }))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown, { capture: true }))
}
