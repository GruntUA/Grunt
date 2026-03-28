/*
 * Dynamic page registry.
 *
 * Discovers Vue page components from two locations:
 *   1. Built-in:  src/apps/{app}/pages/{Page}.vue   (framework-bundled apps)
 *   2. External:  bench/apps/{app}/www/pages/{Page}.vue  (installed apps)
 *
 * Component ID format: "{app_name}/{ComponentName}" (without .vue)
 */

// Built-in app pages (inside framework source)
const builtinModules = import.meta.glob<{ default: unknown }>(
  '../../apps/*/pages/*.vue'
)

// External app pages: bench/apps/*/www/pages/*.vue
// Path is relative from this file (src/core/pages/) to bench/apps/
const externalModules = import.meta.glob<{ default: unknown }>(
  '../../../../../*/www/pages/*.vue'
)

// Build a unified lookup map: "equeue/QueueBoard" -> () => import(...)
const componentRegistry: Record<string, () => Promise<{ default: unknown }>> = {}

// Register built-in: path = "../../apps/{app}/pages/{Component}.vue"
for (const [path, importFn] of Object.entries(builtinModules)) {
  const match = path.match(/apps\/([^/]+)\/pages\/([^/]+)\.vue$/)
  if (match) {
    const [, appName, componentName] = match
    componentRegistry[`${appName}/${componentName}`] = importFn
  }
}

// Register external: path = "../../../../../{app}/www/pages/{Component}.vue"
for (const [path, importFn] of Object.entries(externalModules)) {
  const match = path.match(/\/([^/]+)\/www\/pages\/([^/]+)\.vue$/)
  if (match) {
    const [, appName, componentName] = match
    componentRegistry[`${appName}/${componentName}`] = importFn
  }
}

export function resolvePageComponent(
  componentId: string
): (() => Promise<{ default: unknown }>) | null {
  return componentRegistry[componentId] ?? null
}

export function listRegisteredComponents(): string[] {
  return Object.keys(componentRegistry)
}
