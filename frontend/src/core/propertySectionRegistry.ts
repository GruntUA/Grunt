/**
 * Property Section Registry
 *
 * Single source of truth for PropertiesPanel sections.
 * Core sections are registered in pages/studio/builder/sections/index.ts.
 * Plugin apps can register their own sections before the Vue app mounts:
 *
 *   import { registerPropertySection } from '@/core/propertySectionRegistry'
 *   registerPropertySection('my_section', () => import('./MySection.vue').then(m => m.default))
 *
 * The section component receives `field` and `updateField` via inject (usePropertyEditor).
 */

import type { Component } from 'vue'

export interface PropertySectionDef {
  /** Section name - must match a value in FieldDefinition.propertySections */
  name: string
  /** Async loader for the Vue component that renders this section */
  component: () => Promise<Component>
}

const _registry = new Map<string, PropertySectionDef>()

export function registerPropertySection(name: string, loader: () => Promise<Component>): void {
  _registry.set(name, { name, component: loader })
}

export function getPropertySection(name: string): PropertySectionDef | undefined {
  return _registry.get(name)
}
