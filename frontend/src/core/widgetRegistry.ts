/**
 * Widget Registry
 *
 * Single source of truth for every dashboard widget type in the system —
 * the Dashboard-widget counterpart of fieldRegistry.ts. Core types are
 * registered below via manifest.json auto-discovery. Plugin apps register
 * their own widgets by calling registerWidget() before the Vue app mounts:
 *
 *   import { registerWidget } from '@/core/widgetRegistry'
 *   registerWidget({
 *     type: 'leave_balance',
 *     label: 'Leave balance',
 *     icon: '🏖️',
 *     component: () => import('./LeaveBalanceWidget.vue').then(m => m.default),
 *     configSections: ['title', 'width', 'color'],
 *   })
 *
 * After that the widget appears in:
 *   - the dashboard palette (AppPage)
 *   - WidgetCard (runtime render)
 *   - WidgetConfigPanel (property inspector)
 */

import { defineAsyncComponent, type Component } from 'vue'

// Keep in sync with the sections registered in
// components/dashboard/sections/index.ts
export type WidgetConfigSection =
  | 'title'
  | 'dataSource'
  | 'doctypeSource'
  | 'shortcutTarget'
  | 'activityFilter'
  | 'description'
  | 'textContent'
  | 'tiles'
  | 'links'
  | 'gaugeRange'
  | 'aggregation'
  | 'groupBy'
  | 'dateRange'
  | 'width'
  | 'color'
  | 'icon'

export interface WidgetDefinition {
  /** Unique identifier — matches DashboardWidget.widget_type */
  type: string
  /** Human-readable name shown in the palette and properties panel */
  label: string
  /** Emoji shown in the palette */
  icon: string
  /** Render component used by WidgetCard */
  component: () => Promise<Component>
  /** Property sections shown in WidgetConfigPanel, in order */
  configSections: WidgetConfigSection[]
}

// ── Internal registry ────────────────────────────────────────────────────────

const _registry = new Map<string, WidgetDefinition>()

// ── Public API ────────────────────────────────────────────────────────────────

/** Register a widget type. Can be called from any app before mount. */
export function registerWidget(def: WidgetDefinition): void {
  _registry.set(def.type, def)
}

/** Retrieve a widget definition by type string. */
export function getWidgetDef(type: string): WidgetDefinition | undefined {
  return _registry.get(type)
}

/** All registered widget types, in registration order — drives the palette. */
export function getPaletteWidgets(): WidgetDefinition[] {
  return [..._registry.values()]
}

const _asyncComponentCache = new Map<string, Component>()

/** Get or create a cached defineAsyncComponent instance for a widget type. */
export function getAsyncWidgetComponent(type: string): Component | undefined {
  let comp = _asyncComponentCache.get(type)
  if (!comp) {
    const def = getWidgetDef(type)
    if (!def) return undefined
    comp = defineAsyncComponent(def.component)
    _asyncComponentCache.set(type, comp)
  }
  return comp
}

// ── Discovery ─────────────────────────────────────────────────────────────────

/**
 * Discover and register all widgets from the components/dashboard/widgets/ directory.
 * Each widget lives in its own directory with:
 *  - manifest.json: one definition, or an array of definitions that share a
 *    single component (e.g. chart_area/chart_bar both render Chart.vue)
 *  - [DirName].vue: the render component (by convention — every entry in the
 *    manifest uses this same file, regardless of its own `type`)
 */
type ManifestEntry = Omit<WidgetDefinition, 'component'>

function isValidManifestEntry(v: unknown): v is ManifestEntry {
  return typeof v === 'object' && v !== null
    && typeof (v as any).type === 'string'
    && typeof (v as any).label === 'string'
    && Array.isArray((v as any).configSections)
}

function discoverWidgets() {
  const manifests = import.meta.glob('@/components/dashboard/widgets/*/manifest.json', { eager: true })
  const allVues = import.meta.glob('@/components/dashboard/widgets/*/*.vue')

  for (const path in manifests) {
    try {
      const raw = (manifests[path] as any).default
      const entries: unknown[] = Array.isArray(raw) ? raw : [raw]

      const dirName = path.split('/').at(-2)!
      const searchDir = path.replace('/manifest.json', '/')
      const componentPath = `${searchDir}${dirName}.vue`

      if (!(componentPath in allVues)) {
        console.warn(`[WidgetRegistry] No Vue component found at ${componentPath}`)
        continue
      }
      const component = () => allVues[componentPath]().then((m: any) => m.default as Component)

      for (const entry of entries) {
        if (!isValidManifestEntry(entry)) {
          console.warn(`[WidgetRegistry] Invalid manifest entry at ${path}`)
          continue
        }
        registerWidget({ ...entry, component })
      }
    } catch (e) {
      console.error(`[WidgetRegistry] Failed to register widget from ${path}:`, e)
    }
  }
}

// Initialise registry
discoverWidgets()
