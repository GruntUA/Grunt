/**
 * Dialog components shipped by apps: bench/apps/<app>/desk/dialogs/<Name>.vue,
 * addressed as "<app>/<Name>". A client script opens one with
 *
 *   const result = await grunt.open_dialog('esign/SignDialog', { title, props })
 *
 * The component receives `props` and closes the dialog by emitting `close`
 * with the result. Loaded on first use.
 */
import type { Component } from 'vue'

const modules = import.meta.glob<{ default: Component }>('@apps/*/desk/dialogs/*.vue')

const loaders = new Map<string, () => Promise<Component>>()
for (const [path, load] of Object.entries(modules)) {
  const m = path.match(/([^/]+)\/desk\/dialogs\/([^/]+)\.vue$/)
  if (m) loaders.set(`${m[1]}/${m[2]}`, () => load().then((mod) => mod.default))
}

export function appDialog(name: string): (() => Promise<Component>) | null {
  return loaders.get(name) ?? null
}
