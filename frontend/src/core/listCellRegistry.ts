/**
 * List Cell Registry
 *
 * Resolves the Vue component DataTable / report / cards use to render a cell.
 * A field type gets one by shipping components/fields/<Type>/ListCell.vue
 * (discovered by fieldRegistry). Plugin apps can register or override one
 * before the Vue app mounts:
 *
 *   import { registerListCell } from '@/core/listCellRegistry'
 *   import MyCustomCell from './MyCustomCell.vue'
 *   registerListCell('MyCustomType', MyCustomCell)
 *
 * Each cell component must accept these props:
 *   value:        unknown - raw cell value
 *   row:          Record<string, unknown> - full row data (for __label / __icon suffixes)
 *   field:        DocField - field metadata
 *   statusConfig: DocTypeStatusConfig | null - status config for the doctype
 */

import type { Component } from 'vue'
import DefaultListCell from '@/components/fields/Default/ListCell.vue'
import { byFieldType } from '@/core/fieldRegistry'

// Cells render synchronously inside tables, so they're bundled eagerly here
// (not in fieldRegistry, which must stay light for every importer).
const _discovered = byFieldType(
  import.meta.glob<Component>('@/components/fields/*/ListCell.vue', { eager: true, import: 'default' }),
)
const _registry = new Map<string, Component>()

/** Register a Vue component as the list-cell renderer for a fieldtype. */
export function registerListCell(fieldtype: string, component: Component): void {
  _registry.set(fieldtype, component)
}

/** The cell renderer for a fieldtype - registered, the type's own ListCell.vue, or the default. */
export function getListCell(fieldtype: string): Component {
  return _registry.get(fieldtype) ?? _discovered.get(fieldtype) ?? DefaultListCell
}
