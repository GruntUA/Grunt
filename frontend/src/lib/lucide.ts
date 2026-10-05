/**
 * Lazy, process-wide access to the `@lucide/vue` icon set.
 *
 * The module is large (~1600 icons); importing it once and caching the promise
 * keeps every dynamic-icon field (Button, Icon, …) sharing a single copy
 * instead of triggering a fresh `import()` per component instance.
 */
import type { Component } from 'vue'

type LucideModule = Record<string, Component>

let modPromise: Promise<LucideModule> | null = null

/** The whole icon module, PascalCase keys. Cached after first call. */
export function loadLucideLib(): Promise<LucideModule> {
  // `?all` makes this a separate module instance of the package index, so the
  // full set becomes its own lazy chunk; a plain `import('@lucide/vue')` shares
  // the index with static `import { X } from '@lucide/vue'` and drags every
  // icon into the initial load.
  if (!modPromise) modPromise = import('@lucide/vue?all') as unknown as Promise<LucideModule>
  return modPromise
}

function toPascal(name: string): string {
  return name.includes('-')
    ? name.split('-').map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join('')
    : name.charAt(0).toUpperCase() + name.slice(1)
}

/** kebab-case ("arrow-left") or PascalCase ("ArrowLeft") -> component, or null. */
export async function resolveLucideIcon(
  name: string | null | undefined,
): Promise<Component | null> {
  if (!name) return null
  const lib = await loadLucideLib()
  return (lib[toPascal(name)] as Component | undefined) ?? null
}
