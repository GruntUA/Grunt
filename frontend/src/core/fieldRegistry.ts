/**
 * Field Registry
 *
 * Single source of truth for every field type in the system.
 * Core types are registered below. Plugin apps register their own types
 * by calling registerField() before the Vue app mounts:
 *
 *   import { registerField } from '@/core/fieldRegistry'
 *   import MyGeoField from './MyGeoField.vue'
 *
 *   registerField({
 *     type: 'CustomGeo',
 *     label: 'My Geolocation',
 *     icon: '📍',
 *     category: 'Custom',
 *     component: () => import('./MyGeoField.vue').then(m => m.default),
 *     propertySections: ['core', 'flags', 'display', 'text'],
 *   })
 *
 * After that the field appears in:
 *   - FieldPalette (designer)
 *   - FieldRenderer (runtime form)
 *   - PropertiesPanel (designer)
 */

import type { Component } from 'vue'

export type PropSection =
  | 'core'
  | 'flags'
  | 'display'
  | 'text'
  | 'formula'
  | 'validation'
  | 'default'
  | 'options'
  | 'link'
  | 'table'
  | 'number'
  | 'collapsible'
  | 'aggregate'

export interface FieldDefinition {
  /** Unique identifier — matches DocField.fieldtype */
  type: string
  /** Human-readable name shown in the palette and properties panel */
  label: string
  /** Icon displayed in the palette (emoji or text symbol) */
  icon: string
  /** Group label for the palette (e.g. "Базові", "Медіа") */
  category: string
  /**
   * Layout separators (Section / Column / Tab) — not stored in DB.
   * They are excluded from the draggable palette and handled separately.
   */
  is_layout?: boolean
  /** Whether this item can be dragged from the palette into columns. Default: true */
  draggable?: boolean
  /**
   * Async loader for the Vue component used by FieldRenderer at runtime.
   * Layout fields do not need a component.
   */
  component?: () => Promise<Component>
  /** Property sections shown in PropertiesPanel, in order */
  propertySections: PropSection[]
}

// ── Internal registry ────────────────────────────────────────────────────────

const _registry = new Map<string, FieldDefinition>()

// ── Public API ────────────────────────────────────────────────────────────────

/** Register a field type. Can be called from any app before mount. */
export function registerField(def: FieldDefinition): void {
  _registry.set(def.type, def)
}

/** Retrieve a field definition by type string. */
export function getFieldDef(type: string): FieldDefinition | undefined {
  return _registry.get(type)
}

/** All registered type identifiers. */
export function getAllFieldTypes(): string[] {
  return [..._registry.keys()]
}

/**
 * Returns palette groups for the designer sidebar.
 * Layout fields are excluded — use getLayoutFields() for those.
 * Groups maintain registration order within each category.
 */
export function getPaletteGroups(): Array<{ category: string; fields: FieldDefinition[] }> {
  const groups = new Map<string, FieldDefinition[]>()
  for (const def of _registry.values()) {
    if (def.is_layout) continue
    if (!groups.has(def.category)) groups.set(def.category, [])
    groups.get(def.category)!.push(def)
  }
  return [...groups.entries()].map(([category, fields]) => ({ category, fields }))
}

/** Returns only layout fields (Section, Tab, Column) for the structural palette. */
export function getLayoutFields(): FieldDefinition[] {
  return [..._registry.values()].filter((d) => !!d.is_layout)
}

/**
 * Backward-compatible shim for PropertiesPanel.
 * @deprecated Use getFieldDef() directly.
 */
export function getFieldConfig(type: string): { label: string; sections: PropSection[] } | null {
  const def = _registry.get(type)
  return def ? { label: def.label, sections: def.propertySections } : null
}


/** Fallback component loader for unrecognised field types. */
export const FallbackFieldLoader = (): Promise<Component> =>
  import('@/components/fields/Text/Text.vue').then((m) => m.default as Component)


// ── Core field registrations ─────────────────────────────────────────────────

/**
 * Discover and register all fields from the components/fields/ directory.
 * Each field should be in its own directory with:
 *  - manifest.json: Definition (label, icon, category, propertySections)
 *  - [FieldName].vue: The UI component
 */
async function discoverFields() {
  const manifests = import.meta.glob('@/components/fields/*/manifest.json', { eager: true })
  const components = import.meta.glob('@/components/fields/*/*.vue')

  for (const path in manifests) {
    const config = (manifests[path] as any).default
    // Config should have 'type'
    const fieldType = config.type

    // Find the Vue component in the same dir
    // Path looks like: /src/components/fields/Text/manifest.json
    const searchDir = path.replace('/manifest.json', '/')
    const componentPath = Object.keys(components).find(p => p.startsWith(searchDir) && p.endsWith('.vue'))

    if (componentPath) {
      registerField({
        ...config,
        component: () => components[componentPath]().then((m: any) => m.default as Component)
      })
    } else if (!config.is_layout) {
      console.warn(`[FieldRegistry] No Vue component found for field type "${fieldType}" at ${searchDir}`)
      registerField(config)
    } else {
      // Layout fields don't need a component
      registerField(config)
    }
  }
}

// Initialise registry
discoverFields()

