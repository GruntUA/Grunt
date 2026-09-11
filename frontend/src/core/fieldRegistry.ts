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
 *     icon: 'map-pin',
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

import { defineAsyncComponent, type Component } from 'vue'

/**
 * Storage-class hints for the DocType «Конструктор».
 *
 * Mirrors the backend `column_spec` column mapping (grunt/metadata/field.py) closely
 * enough to tell the user, when they change a field's `fieldtype` in the builder,
 * whether the underlying database column will be retyped — or added / dropped —
 * during the next `doctype sync`. Declared per field type in its own manifest.json,
 * same as `is_layout` — not in a separate lookup table.
 *
 * This is a UI heads-up only. Nothing here mutates the field: existing values
 * are kept as-is and the authoritative migration still runs on sync.
 */
export type StorageClass =
  | 'text' // String / Text column
  | 'int' // Integer column
  | 'float' // Float / Numeric column
  | 'bool' // Boolean column
  | 'date'
  | 'datetime'
  | 'time'
  | 'json' // JSON blob column
  | 'none' // no column of its own (layout, Table, MultiLink, Button, …)

// Keep in sync with the sections registered in
// pages/studio/builder/sections/index.ts
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
  | 'fetch_from'
  | 'table'
  | 'number'
  | 'collapsible'
  | 'aggregate'
  | 'icon'
  | 'button'
  | 'tab'

export interface FieldDefinition {
  /** Unique identifier — matches DocField.fieldtype */
  type: string
  /** Human-readable name shown in the palette and properties panel */
  label: string
  /** Icon displayed in the palette — kebab-case Lucide name (e.g. "calendar-clock") or emoji fallback */
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
  /**
   * Optional override for the designer canvas preview.
   * If absent, CanvasFieldCard renders the real `component` with disabled=true.
   * Use this only for heavy or canvas-based fields (Code editor, Signature, etc.)
   * where the full runtime component is too expensive for a small preview card.
   */
  designerPreview?: () => Promise<Component>
  /** Property sections shown in PropertiesPanel, in order */
  propertySections: PropSection[]
  /** If true, this field cannot be used as a 'Group By' criterion in lists. Default: false */
  non_groupable?: boolean
  /** How this field's value is stored in the DB column. Unknown / plugin types default to 'text'. */
  storage_class?: StorageClass
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

/** Set of layout field type strings (Section, Column, Tab) — use instead of hardcoded Sets. */
export function getLayoutTypeSet(): Set<string> {
  return new Set([..._registry.values()].filter((d) => !!d.is_layout).map((d) => d.type))
}

/** Layout types + non-physical container types (Table, MultiLink) that have no DB column. */
export function getNonPhysicalTypeSet(): Set<string> {
  return new Set([...getLayoutTypeSet(), 'Table', 'MultiLink'])
}

/** Storage class for a field type. Unknown / plugin types are assumed text. */
export function getStorageClass(type: string): StorageClass {
  return getFieldDef(type)?.storage_class ?? 'text'
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

const _asyncComponentCache = new Map<string, Component>()

/** Get or create a cached defineAsyncComponent instance for a field type. */
export function getAsyncFieldComponent(type: string): Component {
  let comp = _asyncComponentCache.get(type)
  if (!comp) {
    const loader = getFieldDef(type)?.component ?? FallbackFieldLoader
    comp = defineAsyncComponent(loader)
    _asyncComponentCache.set(type, comp)
  }
  return comp
}


// ── Core field registrations ─────────────────────────────────────────────────

/**
 * Discover and register all fields from the components/fields/ directory.
 * Each field should be in its own directory with:
 *  - manifest.json: Definition (label, icon, category, propertySections)
 *  - [FieldName].vue: The UI component
 */
function isValidManifest(v: unknown): v is Omit<FieldDefinition, 'component' | 'designerPreview'> {
  return typeof v === 'object' && v !== null
    && typeof (v as any).type === 'string'
    && typeof (v as any).label === 'string'
    && Array.isArray((v as any).propertySections)
}

async function discoverFields() {
  const manifests = import.meta.glob('@/components/fields/*/manifest.json', { eager: true })
  const allVues = import.meta.glob('@/components/fields/*/*.vue')

  for (const path in manifests) {
    try {
      const config = (manifests[path] as any).default
      if (!isValidManifest(config)) {
        console.warn(`[FieldRegistry] Invalid manifest at ${path}`)
        continue
      }

      const dirName = path.split('/').at(-2)!  // e.g. "Check", "Rating"
      const searchDir = path.replace('/manifest.json', '/')

      // Main runtime component: {DirName}/{DirName}.vue (exact match by convention)
      const componentPath = `${searchDir}${dirName}.vue`
      // Designer preview: {DirName}/DesignerPreview.vue
      const previewPath = `${searchDir}DesignerPreview.vue`

      const entry: FieldDefinition = { ...(config as any) }

      if (componentPath in allVues) {
        entry.component = () => allVues[componentPath]().then((m: any) => m.default as Component)
      } else if (!config.is_layout) {
        console.warn(`[FieldRegistry] No Vue component found for field type "${config.type}" at ${searchDir}`)
      }

      if (previewPath in allVues) {
        entry.designerPreview = () => allVues[previewPath]().then((m: any) => m.default as Component)
      }

      registerField(entry)
    } catch (e) {
      console.error(`[FieldRegistry] Failed to register field from ${path}:`, e)
    }
  }
}

// Initialise registry
discoverFields()

