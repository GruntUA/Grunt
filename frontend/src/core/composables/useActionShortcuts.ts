import { onBeforeUnmount, onMounted } from 'vue'

import { matchesShortcut, type ActionRegistry } from '@/core/actions'

/**
 * Keyboard shortcuts declared by actions (`shortcut: 'Ctrl+S'`): a visible,
 * enabled action whose shortcut matches runs, and the browser default
 * (e.g. «Save page») is suppressed. Works while typing in a field.
 */
export function useActionShortcuts(registry: ActionRegistry) {
  function onKeydown(event: KeyboardEvent) {
    if (event.defaultPrevented || event.repeat) return
    const action = registry.withShortcut().find((a) => a.shortcut && matchesShortcut(event, a.shortcut))
    if (!action) return
    event.preventDefault()
    void action.run()
  }
  onMounted(() => window.addEventListener('keydown', onKeydown))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
}
