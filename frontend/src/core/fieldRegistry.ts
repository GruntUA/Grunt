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
 *
 * Built-in types are discovered from components/fields/<Type>/ by file name:
 *   manifest.json        - the definition below (storage_class / traits are
 *                          written by `grunt fields sync-manifests`)
 *   <Type>.vue           - the form component
 *   DesignerPreview.vue  - optional canvas preview
 *   ListCell.vue         - optional list / report cell (see listCellRegistry)
 *   FilterInput.vue      - optional filter value input (see filterRegistry)
 *   PropertySection.vue  - optional designer section of its own (see propertySectionRegistry)
 */

import { defineAsyncComponent, type Component } from 'vue'

/**
 * How a field type's value is stored in the DB column ('text', 'int', 'float',
 * 'bool', 'date', 'datetime', 'time', 'json', or 'none' for types with no column
 * of their own). Derived from FieldType.column_spec - see get_storage_class() in
 * grunt/metadata/field.py - and written to each manifest.json by
 * `grunt fields sync-manifests`; not listed here.
 */
export type StorageClass = string

/**
 * What the rest of the UI may assume about a type's value ('link', 'table',
 * 'file', …). The vocabulary is TRAITS in grunt/metadata/field.py, synced into
 * each manifest.json - ask hasTrait() instead of listing fieldtype names.
 * Numeric / date-ness is not a trait: it follows from storage_class
 * (isNumericType / isDateType).
 */
export type FieldTrait = string

/**
 * PropertiesPanel section name - whatever registerPropertySection() registered
 * (core sections: pages/studio/builder/sections/index.ts; plugins add their own).
 */
export type PropSection = string

export interface FieldDefinition {
  /** Unique identifier - matches DocField.fieldtype */
  type: string
  /** Human-readable name shown in the palette and properties panel */
  label: string
  /** Icon displayed in the palette - kebab-case Lucide name (e.g. "calendar-clock") or emoji fallback */
  icon: string
  /** Group label for the palette (e.g. "Базові", "Медіа") */
  category: string
  /**
   * Layout separators (Section / Column / Tab) - not stored in DB.
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
  /** Value traits - synced from the backend FieldType. */
  traits?: FieldTrait[]
  /** The component renders its own label, so FieldRenderer doesn't add one. */
  own_label?: boolean
  /** Extra events the component emits that FieldRenderer forwards (e.g. 'create-new'). */
  emits?: string[]
  /** Edited right in a Table grid cell; otherwise only in the row sheet. */
  table_inline?: boolean
  /** Its raw value is edited as plain text by double-click in a list cell. */
  list_inline?: boolean
  /** Aggregate a report starts a column with ('sum' when absent) - e.g. 'avg' for Percent. */
  default_agg?: string
  /** false - not offered in the Web Form designer palette (needs UI a plain form lacks). Default: true */
  webform?: boolean
  /** QuickFilter.input_type for this type ('text', 'date', 'select', …); absent - not offered as a quick filter. */
  quick_filter?: string
  /** Filter operators, when the ones derived from storage_class / traits don't fit. A type with
   *  no column of its own (storage_class 'none') is offered in the filter bar only with these -
   *  e.g. MultiLink, which the backend filters through its junction table. */
  filter_ops?: string[]
}

// Internal registry

const _registry = new Map<string, FieldDefinition>()

// Public API

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
 * Layout fields are excluded - use getLayoutFields() for those.
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

/** Set of layout field type strings (Section, Column, Tab) - use instead of hardcoded Sets. */
export function getLayoutTypeSet(): Set<string> {
  return new Set([..._registry.values()].filter((d) => !!d.is_layout).map((d) => d.type))
}

/** Types with no DB column of their own (layout, Table, MultiLink, Button, HTML…) - per manifest storage_class. */
export function getNonPhysicalTypeSet(): Set<string> {
  return new Set([..._registry.values()].filter((d) => !!d.is_layout || d.storage_class === 'none').map((d) => d.type))
}

/** Types the filter bar offers - with a DB column, or with explicit manifest filter_ops. */
export function isFilterableType(type: string): boolean {
  const def = _registry.get(type)
  if (def?.filter_ops?.length) return true
  return !getNonPhysicalTypeSet().has(type)
}

/** Types edited right in a Table grid cell - per manifest table_inline. */
export function getTableInlineTypeSet(): Set<string> {
  return new Set([..._registry.values()].filter((d) => !!d.table_inline).map((d) => d.type))
}

/** Types edited as plain text right in a list cell - per manifest list_inline. */
export function getListInlineTypeSet(): Set<string> {
  return new Set([..._registry.values()].filter((d) => !!d.list_inline).map((d) => d.type))
}

/** Types that can be offered as a quick filter - per manifest quick_filter. */
export function getQuickFilterTypeSet(): Set<string> {
  return new Set([..._registry.values()].filter((d) => !!d.quick_filter).map((d) => d.type))
}

/** Storage class for a field type. Unknown / plugin types are assumed text. */
export function getStorageClass(type: string): StorageClass {
  return getFieldDef(type)?.storage_class ?? 'text'
}

/** True if the field type declares `trait`. */
export function hasTrait(type: string, trait: FieldTrait): boolean {
  return !!getFieldDef(type)?.traits?.includes(trait)
}

/** True if the field type stores a number (Int, Float, Currency, Percent, Duration, Rating…). */
export function isNumericType(type: string): boolean {
  const sc = getStorageClass(type)
  return sc === 'int' || sc === 'float'
}

/** True if the field type holds a single choice from its `options` (Select) - MultiSelect's list is not. */
export function isChoiceType(type: string): boolean {
  return hasTrait(type, 'options') && getStorageClass(type) === 'text'
}

/** True if the field type stores a calendar date (Date or Datetime). */
export function isDateType(type: string): boolean {
  const sc = getStorageClass(type)
  return sc === 'date' || sc === 'datetime'
}

/**
 * Key an `import.meta.glob` result over components/fields/<Type>/<file> by field
 * type (its folder name) - for registries discovering optional per-type files
 * such as ListCell.vue / FilterInput.vue / format.ts.
 */
export function byFieldType<T>(modules: Record<string, T>): Map<string, T> {
  return new Map(Object.entries(modules).map(([path, mod]) => [path.split('/').at(-2)!, mod]))
}

/** Component loader for a field type - throws for a type nobody registered. */
export function getFieldLoader(type: string): () => Promise<Component> {
  const loader = getFieldDef(type)?.component
  if (!loader) throw new Error(`[FieldRegistry] Unknown field type "${type}"`)
  return loader
}

const _asyncComponentCache = new Map<string, Component>()

/** Get or create a cached defineAsyncComponent instance for a field type. */
export function getAsyncFieldComponent(type: string): Component {
  let comp = _asyncComponentCache.get(type)
  if (!comp) {
    comp = defineAsyncComponent(getFieldLoader(type))
    _asyncComponentCache.set(type, comp)
  }
  return comp
}


// Core field registrations

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

function discoverFields() {
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

