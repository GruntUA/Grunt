/**
 * Widget Config Section Registry
 *
 * Single source of truth for WidgetConfigPanel sections — the widget
 * counterpart of propertySectionRegistry.ts. Kept as its own registry
 * (rather than sharing the field one) because section names are chosen
 * independently in each domain and can collide (e.g. both a field and a
 * widget may reasonably want a section named "icon").
 *
 * Core sections are registered in components/dashboard/sections/index.ts.
 * Plugin apps can register their own sections before the Vue app mounts:
 *
 *   import { registerWidgetSection } from '@/core/widgetSectionRegistry'
 *   registerWidgetSection('my_section', () => import('./MySection.vue').then(m => m.default))
 *
 * The section component receives `widget` and `updateWidget` via inject
 * (useWidgetPropertyEditor).
 */

import type { Component } from 'vue'

export interface WidgetSectionDef {
  name: string
  component: () => Promise<Component>
}

const _registry = new Map<string, WidgetSectionDef>()

export function registerWidgetSection(name: string, loader: () => Promise<Component>): void {
  _registry.set(name, { name, component: loader })
}

export function getWidgetSection(name: string): WidgetSectionDef | undefined {
  return _registry.get(name)
}
