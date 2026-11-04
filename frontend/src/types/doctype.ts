/** DocType metadata: permissions, view configs, status, links, actions. */

import type { DocField } from './field'

export interface DocTypeSummary {
  name: string
  label: string
  module: string
  is_child?: boolean
  is_singleton?: boolean
}

export interface DocType {
  name: string
  label: string
  module: string
  description?: string | null
  icon?: string | null
  app?: string | null
  is_child?: boolean
  is_singleton?: boolean
  is_virtual?: boolean
  is_tree?: boolean
  track_changes?: boolean
  track_seen?: boolean
  track_views?: boolean
  quick_entry?: boolean
  show_preview_popup?: boolean
  /** Documents can carry qualified electronic signatures (an e-signature app adds the UI). */
  is_signable?: boolean
  beta?: boolean
  deprecated?: boolean
  table_name?: string | null
  fields: DocField[]
  title_field?: string
  image_field?: string | null
  search_fields?: string[]
  /** Composite (multi-column) indexes - [["reference_doctype", "reference_id"]]. */
  indexes?: string[][]
  autoname?: string | null
  default_view?: string | null
  /** List order when none is chosen (backend falls back to modified_at desc). */
  sort_field?: string | null
  sort_order?: 'asc' | 'desc'
  form_show_sidebar?: boolean
  kanban_column_field?: string | null
  calendar_date_field?: string | null
  calendar_end_date_field?: string | null
  calendar_title_field?: string | null
  calendar_sources?: CalendarSource[]
  gantt_start_field?: string | null
  gantt_end_field?: string | null
  gantt_title_field?: string | null
  gantt_progress_field?: string | null
  gantt_color_field?: string | null
  gantt_color_map?: Record<string, string> | null
  gantt_default_color?: string | null
  gantt_dependencies_field?: string | null
  tree_parent_field?: string | null
  tree_title_field?: string | null
  tree_as_of_date_field?: string | null
  tree_sort_by?: string | null
  tree_sort_order?: 'asc' | 'desc'
  shares_cover_subtree?: boolean
  map_view?: DocTypeMapView | null
  status_field?: string | null
  status_indicators?: StatusIndicator[]
  workflow_state_field?: string | null
  permissions?: DocPermission[]
  actions?: DocTypeActionBinding[]
  /** Registry metadata for every action bind-able on this DocType (Studio helper). */
  _action_catalog?: DocActionCatalogEntry[]
  links?: DocTypeLink[]
}

export interface DocPermission {
  role: string
  read?: boolean
  write?: boolean
  create?: boolean
  delete?: boolean
  report?: boolean
  match?: string | null
  hidden_fields?: string[]
}

export interface CalendarSource {
  ref_doctype: string
  date_field: string
  end_date_field?: string
  label_field?: string
  color?: string
  filters?: Record<string, string>
  recurring?: boolean
  event_type?: 'default' | 'birthday'
  show_age?: boolean
}

export interface DocTypeMapView {
  geo_field?: string                  // override auto-detected Geolocation field
  label_field?: string                // field shown in marker popup (defaults to title_field)
  color_field?: string                // field whose value drives marker color
  color_map?: Record<string, string>  // { value: '#hex' } mapping for color_field
  default_color?: string              // fallback marker color (defaults to primary)
  icon_field?: string                 // field containing a lucide icon name for the marker
}

export interface StatusIndicator {
  value: string
  color: string
  icon?: string | null
  label?: string | null
}

/**
 * Runtime bundle passed to list cells / exporters. Assembled from a DocType's
 * `status_field` + `status_indicators` by `statusConfigOf()` - it is not stored
 * on the DocType itself.
 */
export interface DocTypeStatusConfig {
  field: string
  indicators: StatusIndicator[]
}

/** One row of the DocType `links` table - a related DocType surfaced on the
 *  document "Зв'язки" panel. */
export interface DocTypeLink {
  link_doctype: string
  link_fieldname?: string
  parent_doctype?: string | null
  table_fieldname?: string | null
  group?: string
  label?: string
  hidden?: boolean
}

/** `grunt.document.connections.get_connections` response. */
export interface DocConnectionsResult {
  groups: {
    name: string
    links: {
      link_doctype: string
      label: string
      fieldname: string
      via_child: boolean
      count: number
      preview: { name: string; title: string }[]
    }[]
  }[]
}

/** Input field an action prompts for before running - a subset of the
 *  `DialogField` shape consumed by `useDialog().form()`. */
export interface DocActionField {
  fieldname: string
  label: string
  fieldtype?: string
  required?: boolean
  default?: unknown
  options?: string
  description?: string
}

/** One row of the DocType `actions` table - binds a registered action, with
 *  optional presentation overrides. Keys prefixed `_` are resolved server-side
 *  from the code registry (see grunt.actions). */
export interface DocTypeActionBinding {
  action: string
  label?: string
  group?: string
  variant?: string
  condition?: string | null
  hidden?: boolean
  // Server-resolved (grunt.api.v1.meta._dump_doctype):
  _label?: string
  _icon?: string | null
  _variant?: string
  _group?: string
  _confirm?: string | null
  _fields?: DocActionField[]
  _missing?: boolean
}

export interface DocActionCatalogEntry {
  key: string
  label: string
  icon?: string | null
  group?: string
  variant?: string
  confirm?: string | null
  module?: string
}
