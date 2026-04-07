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
  | 'validation'
  | 'default'
  | 'options'
  | 'link'
  | 'table'
  | 'number'
  | 'collapsible'

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
  import('@/components/fields/FieldText.vue').then((m) => m.default as Component)

// ── Core field registrations ─────────────────────────────────────────────────

const DATA: PropSection[] = ['core', 'flags', 'display', 'text', 'default']

// Базові
registerField({ type: 'Text',     label: 'Text',      icon: 'T',   category: 'Базові',
  component: () => import('@/components/fields/FieldText.vue').then(m => m.default as Component),
  propertySections: [...DATA, 'validation'] })

registerField({ type: 'LongText', label: 'Long Text', icon: '¶',   category: 'Базові',
  component: () => import('@/components/fields/FieldLongText.vue').then(m => m.default as Component),
  propertySections: [...DATA, 'validation'] })

registerField({ type: 'Int',      label: 'Integer',   icon: '#',   category: 'Базові',
  component: () => import('@/components/fields/FieldInt.vue').then(m => m.default as Component),
  propertySections: [...DATA, 'number', 'validation'] })

registerField({ type: 'Float',    label: 'Float',     icon: '.1',  category: 'Базові',
  component: () => import('@/components/fields/FieldFloat.vue').then(m => m.default as Component),
  propertySections: [...DATA, 'number', 'validation'] })

registerField({ type: 'Check',    label: 'Checkbox',  icon: '✓',   category: 'Базові',
  component: () => import('@/components/fields/FieldCheck.vue').then(m => m.default as Component),
  propertySections: ['core', 'flags', 'display', 'text', 'default'] })

registerField({ type: 'Color',    label: 'Color',     icon: '🎨',  category: 'Базові',
  component: () => import('@/components/fields/FieldColor.vue').then(m => m.default as Component),
  propertySections: DATA })

// Дата і час
registerField({ type: 'Date',     label: 'Date',      icon: '📅',  category: 'Дата і час',
  component: () => import('@/components/fields/FieldDate.vue').then(m => m.default as Component),
  propertySections: DATA })

registerField({ type: 'Datetime', label: 'Datetime',  icon: '🕐',  category: 'Дата і час',
  component: () => import('@/components/fields/FieldDatetime.vue').then(m => m.default as Component),
  propertySections: DATA })

registerField({ type: 'Time',     label: 'Time',      icon: '⏰',  category: 'Дата і час',
  component: () => import('@/components/fields/FieldText.vue').then(m => m.default as Component),
  propertySections: DATA })

// Вибір і зв'язки
registerField({ type: 'Select',    label: 'Select',    icon: '▼',    category: "Вибір і зв'язки",
  component: () => import('@/components/fields/FieldSelect.vue').then(m => m.default as Component),
  propertySections: [...DATA, 'options'] })

registerField({ type: 'Link',      label: 'Link',      icon: '🔗',   category: "Вибір і зв'язки",
  component: () => import('@/components/fields/FieldLink.vue').then(m => m.default as Component),
  propertySections: [...DATA, 'link'] })

registerField({ type: 'MultiLink', label: 'Multi Link', icon: '⛓',  category: "Вибір і зв'язки",
  component: () => import('@/components/fields/FieldMultiLink.vue').then(m => m.default as Component),
  propertySections: [...DATA, 'link'] })

// Медіа
registerField({ type: 'Attach', label: 'Attach', icon: '📎', category: 'Медіа',
  component: () => import('@/components/fields/FieldAttach.vue').then(m => m.default as Component),
  propertySections: DATA })

registerField({ type: 'Image',  label: 'Image',  icon: '🖼',  category: 'Медіа',
  component: () => import('@/components/fields/FieldImage.vue').then(m => m.default as Component),
  propertySections: DATA })

// Текст
registerField({ type: 'RichText', label: 'Rich Text', icon: '✍',  category: 'Текст',
  component: () => import('@/components/fields/FieldRichText.vue').then(m => m.default as Component),
  propertySections: DATA })

registerField({ type: 'JSON', label: 'JSON', icon: '{}', category: 'Текст',
  component: () => import('@/components/fields/FieldJson.vue').then(m => m.default as Component),
  propertySections: DATA })

registerField({ type: 'Code', label: 'Code', icon: '<>', category: 'Текст',
  component: () => import('@/components/fields/FieldCode.vue').then(m => m.default as Component),
  propertySections: [...DATA, 'options'] })

// Таблиці
registerField({ type: 'Table', label: 'Table', icon: '▦', category: 'Таблиці',
  component: () => import('@/components/fields/FieldTable.vue').then(m => m.default as Component),
  propertySections: ['core', 'flags', 'display', 'text', 'table'] })

// Спеціальні
registerField({ type: 'Signature',   label: 'Signature',   icon: '✏',  category: 'Спеціальні',
  component: () => import('@/components/fields/FieldText.vue').then(m => m.default as Component),
  propertySections: ['core', 'flags', 'display', 'text'] })

registerField({ type: 'Geolocation', label: 'Geolocation', icon: '📍', category: 'Спеціальні',
  component: () => import('@/components/fields/FieldGeolocation.vue').then(m => m.default as Component),
  propertySections: ['core', 'flags', 'display', 'text'] })

registerField({ type: 'BarCode', label: 'Barcode / QR', icon: '▌▌', category: 'Спеціальні',
  component: () => import('@/components/fields/FieldBarcode.vue').then(m => m.default as Component),
  propertySections: ['core', 'flags', 'display', 'text'] })

// Структурні (layout-only, not DB-backed)
registerField({ type: 'Section', label: 'Section', icon: '═', category: '', is_layout: true,
  propertySections: ['core', 'collapsible', 'text'] })

registerField({ type: 'Column', label: 'Column', icon: '║', category: '', is_layout: true,
  propertySections: ['core'] })

registerField({ type: 'Tab', label: 'Tab', icon: '⊟', category: '', is_layout: true,
  propertySections: ['core'] })
