/*
 * Dynamic page registry.
 *
 * Auto-discovers Vue components from src/apps/{app}/pages/{Page}.vue
 * and provides them for dynamic route registration.
 *
 * Component ID format: "{app_name}/{ComponentName}" (without .vue)
 */

// Vite glob import — discovers all app page components at build time
const pageModules = import.meta.glob<{ default: unknown }>(
  '../../apps/*/pages/*.vue'
)

// Build a lookup map: "cnap/CnapDashboard" -> () => import(...)
const componentRegistry: Record<string, () => Promise<{ default: unknown }>> = {}

for (const [path, importFn] of Object.entries(pageModules)) {
  // path looks like: ../../apps/cnap/pages/CnapDashboard.vue
  const match = path.match(/apps\/([^/]+)\/pages\/([^/]+)\.vue$/)
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
