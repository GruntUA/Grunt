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
 */
export function useActionShortcuts(registry: ActionRegistry) {
  function onKeydown(event: KeyboardEvent) {
    if (event.defaultPrevented) return
    const action = registry.withShortcut().find((a) => a.shortcut && matchesShortcut(event, a.shortcut))
    if (!action) return
    event.preventDefault()
    // Held keys repeat: suppress «Save page» for every repeat, run once.
    if (!event.repeat) void action.run()
  }
  onMounted(() => window.addEventListener('keydown', onKeydown, { capture: true }))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown, { capture: true }))
}
