import { shallowRef, type Component } from 'vue'

import { loadLucideLib } from '@/lib/lucide'

// Module-level: one reactive handle on the shared icon set for every caller.
const icons = shallowRef<Record<string, Component> | null>(null)
let requested = false

function load() {
  if (requested) return
  requested = true
  loadLucideLib().then((lib) => { icons.value = lib })
}

/**
 * Resolves Lucide icons by the name stored in metadata. The whole icon set is
 * a separate lazy chunk, so `iconFor` returns `null` until it arrives and
 * re-evaluates reactively once it does; unknown names yield `fallback`.
 */
export function useLucideIcons() {
  load()

  function iconFor(name?: string | null, fallback: Component | null = null): Component | null {
    if (!name) return fallback
    if (!icons.value) return null
    return icons.value[name] ?? fallback
  }

  return { iconFor }
}
