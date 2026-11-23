/**
 * Dialog components shipped by apps: bench/apps/<app>/desk/dialogs/<Name>.vue,
 * addressed as "<app>/<Name>". A client script opens one with
 *
 *   const result = await grunt.open_dialog('esign/SignDialog', { title, props })
 *
 * The component receives `props` and closes the dialog by emitting `close`
 * with the result. Loaded on first use.
 *
 * The core's own dialogs (src/components/desk/dialogs/<Name>.vue) are
 * "grunt/<Name>" - e.g. 'grunt/NotificationPreferences'.
 */
import type { Component } from 'vue'

const modules = import.meta.glob<{ default: Component }>('@apps/*/desk/dialogs/*.vue')
const core = import.meta.glob<{ default: Component }>('@/components/desk/dialogs/*.vue')

const loaders = new Map<string, () => Promise<Component>>()
for (const [path, load] of Object.entries(core)) {
  const m = path.match(/\/([^/]+)\.vue$/)
  if (m) loaders.set(`grunt/${m[1]}`, () => load().then((mod) => mod.default))
}
for (const [path, load] of Object.entries(modules)) {
  const m = path.match(/([^/]+)\/desk\/dialogs\/([^/]+)\.vue$/)
  if (m) loaders.set(`${m[1]}/${m[2]}`, () => load().then((mod) => mod.default))
}

export function appDialog(name: string): (() => Promise<Component>) | null {
  return loaders.get(name) ?? null
}
