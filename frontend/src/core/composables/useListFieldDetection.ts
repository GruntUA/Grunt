import { computed, ComputedRef } from 'vue'
import type { DocType, DocField } from '@/types'

/**
 * Detects and resolves specialized fields for various list view modes.
 * Handles finding the kanban column field, tree parent field, geolocation field,
 * and calendar date field based on DocType configuration and field metadata.
 */
export function useListFieldDetection(doctype: ComputedRef<DocType | null>) {
  /**
   * Kanban column field: First Select field marked as in_list_view
   */
  const kanbanColumnField = computed(() => {
    const dt = doctype.value
    if (!dt) return null
    return dt.fields.find(f => f.fieldtype === 'Select' && f.in_list_view && !f.hidden) ?? null
  })

  /**
   * Tree parent field: configured via tree_view.parent_field or auto-detect self-link
   */
  const treeParentField = computed(() => {
    const dt = doctype.value
    if (!dt) return null
    if (dt.tree_view?.parent_field) {
      return dt.fields.find(f => f.fieldname === dt.tree_view!.parent_field) ?? null
    }
    // Auto-detect: Link field pointing to self
    return dt.fields.find(f => f.fieldtype === 'Link' && f.options === dt.name) ?? null
  })

  /**
   * Geolocation field: configured via map_view.geo_field or auto-detect first Geolocation field
   */
  const geoField = computed(() => {
    const dt = doctype.value
    if (!dt) return null
    const override = dt.map_view?.geo_field
    if (override) {
      return dt.fields.find(f => f.fieldname === override) ?? null
    }
    // Auto-detect: First Geolocation field in list view
    return dt.fields.find(f => f.fieldtype === 'Geolocation' && f.in_list_view && !f.hidden) ?? null
  })

  /**
   * Calendar date field: configured via calendar_view.field or auto-detect Date/Datetime field
   */
  const calendarDateField = computed(() => {
    const dt = doctype.value
    if (!dt) return null
    const f = dt.calendar_view?.field
    // Handle system fields (created_at, modified_at) by synthesizing DocField objects
    if (f && new Set(['created_at', 'modified_at']).has(f)) {
      return { fieldname: f, fieldtype: 'Datetime', label: f } as DocField
    }
    // Configured field
    if (f && dt.fields.find(field => field.fieldname === f)) {
      return dt.fields.find(field => field.fieldname === f) ?? null
    }
    // Auto-detect: first Date or Datetime field
    return (
      dt.fields.find(field => field.fieldtype === 'Date' || field.fieldtype === 'Datetime') || null
    )
  })

  return {
    kanbanColumnField,
    treeParentField,
    geoField,
    calendarDateField,
  }
}
