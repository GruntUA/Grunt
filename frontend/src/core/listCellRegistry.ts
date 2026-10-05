/**
 * List Cell Registry
 *
 * Maps fieldtype strings -> Vue components used by DataTable to render cells.
 * Built-in renderers are registered in app-hooks.ts.
 * External apps can register custom renderers before the Vue app mounts:
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

const _registry = new Map<string, Component>()

/** Register a Vue component as the list-cell renderer for a fieldtype. */
export function registerListCell(fieldtype: string, component: Component): void {
  _registry.set(fieldtype, component)
}

/** Retrieve the registered renderer for a fieldtype, or null if none. */
export function getListCell(fieldtype: string): Component | null {
  return _registry.get(fieldtype) ?? null
}
