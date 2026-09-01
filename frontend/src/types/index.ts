/**
 * Field type identifier. Fully open — the real set is resolved at runtime by
 * the field registry (src/core/fieldRegistry.ts), which discovers core types
 * from the manifest.json files under components/fields/ and lets any plugin
 * app add its own via registerField().
 */
export type FieldType = string

/** Standard props contract for runtime field components */
export interface BaseFieldProps {
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}

export interface IndexHint {
  field: string
  reason: string
}

export interface DocField {
  fieldname: string
  label: string
  fieldtype: FieldType
  // Validation
  required?: boolean
  unique?: boolean
  index?: boolean
  read_only?: boolean
  hidden?: boolean
  bold?: boolean
  // Display
  in_list_view?: boolean
  in_filter?: boolean
  in_quick_filter?: boolean
  // Type-specific
  options?: string
  // Name of a backend registry source whose values replace `options` — see
  // grunt.metadata.dynamic_options. Already resolved into `options` by the
  // time the schema reaches the frontend; kept here for completeness.
  options_source?: string | null
  // Name of a backend schema registry source (grunt.metadata.dynamic_options)
  // whose {key: fields} variants are resolved into `dynamic_schemas` at
  // schema-serve time. `dynamic_schema_key` names the sibling field in the
  // same row whose value selects which variant applies.
  dynamic_schema_source?: string | null
  dynamic_schema_key?: string | null
  dynamic_schemas?: Record<string, DocField[]>
  default?: unknown
  description?: string
  placeholder?: string
  // Validation rules
  min_value?: number
  max_value?: number
  max_length?: number
  regex?: string
  // Conditional
  depends_on?: string
  mandatory_depends_on?: string
  formula?: string | null
  // Aggregation
  aggregate_function?: string | null
  aggregate_table?: string | null
  aggregate_field?: string | null
  // Link
  link_filters?: string | null
  // Quick Entry
  in_quick_entry?: boolean
  // Layout
  columns?: number
  collapsible?: boolean
  /** Tab fields only — render the "Зв'язки" (connections) panel inside this tab. */
  show_connections?: boolean
  icon?: string
  experimental_component?: string
  // Virtual
  is_virtual?: boolean
  read_formula?: string | null
  // Fetch From
  fetch_from?: string | null
  // Named validator (e.g. "email", "phone", "url", "iban_ua")
  validator?: string | null
  // Password field — show a live checklist of the SystemSettings password policy.
  show_strength?: boolean
  // Table field — group rows by this child fieldname
  group_by?: string | null
}

export interface DocTypeSummary {
  name: string
  label: string
  module: string
  is_child?: boolean
  is_singleton?: boolean
}

// ── Permission types ──────────────────────────────────────────────────────

export interface DocPermission {
  role: string
  read?: boolean
  write?: boolean
  create?: boolean
  delete?: boolean
  submit?: boolean
  report?: boolean
  match?: string | null
  hidden_fields?: string[]
}

// ── View configuration types ─────────────────────────────────────────────

export interface CalendarSource {
  doctype: string
  date_field: string
  end_date_field?: string
  label_field?: string
  color?: string
  filters?: Record<string, string>
  recurring?: boolean
  event_type?: 'default' | 'birthday'
  show_age?: boolean
}

export interface DocTypeCalendarView {
  field: string
  end_field?: string
  title_field?: string
  sources?: CalendarSource[]
}

// ── Quick filter types ─────────────────────────────────────────────────────

export interface QuickFilterOnChange {
  mode: 'local' | 'external'
  source?: string
  debounce_ms?: number
}

export interface QuickFilter {
  id: string
  field: string
  operator: string
  label?: string
  input_type: string  // 'text' | 'date' | 'select' | 'check' | 'number' | 'link'
  default_value?: string | null
  /** Explicit list of select options; overrides field.options when set */
  options?: string[] | null
  on_change: QuickFilterOnChange
  enabled_in: Array<'list' | 'tree'>
}

/** A single active filter — used by FilterBar, DocTypeList, and docsApi */
export interface ActiveFilter {
  fieldname: string
  label: string
  fieldtype?: string   // stored for display logic in chips
  op: string          // display op: '=', '!=', 'like', '>', '<', '>=', '<='
  value: string
  displayValue?: string  // human-readable label (Link fields: title instead of name)
}

export interface DocTypeMapView {
  geo_field?: string                  // override auto-detected Geolocation field
  label_field?: string                // field shown in marker popup (defaults to title_field)
  color_field?: string                // field whose value drives marker color
  color_map?: Record<string, string>  // { value: '#hex' } mapping for color_field
  default_color?: string              // fallback marker color (defaults to primary)
  icon_field?: string                 // field containing a lucide icon name for the marker
}

export interface ScriptButton {
  label: string
  action: () => void | Promise<void>
  severity?: string
  className?: string
  icon?: string
  group?: string
}

/** Item registered via `listview.add_menu_item()` — appears in the "⋯" header dropdown. */
export interface ScriptMenuItem {
  label: string
  action: () => void | Promise<void>
  icon?: string           // reserved for future icon support
  separator_before?: boolean
}

// ── Status indicators ────────────────────────────────────────────────────

export interface StatusIndicator {
  value: string
  color: string
  icon?: string | null
  label?: string | null
}

/**
 * Runtime bundle passed to list cells / exporters. Assembled from a DocType's
 * `status_field` + `status_indicators` by `statusConfigOf()` — it is not stored
 * on the DocType itself.
 */
export interface DocTypeStatusConfig {
  field: string
  indicators: StatusIndicator[]
}

// ── DocType ───────────────────────────────────────────────────────────────

export interface DocType {
  name: string
  label: string
  module: string
  description?: string | null
  icon?: string | null
  app?: string | null
  is_child?: boolean
  is_submittable?: boolean
  is_singleton?: boolean
  is_virtual?: boolean
  is_tree?: boolean
  track_changes?: boolean
  track_seen?: boolean
  track_views?: boolean
  quick_entry?: boolean
  beta?: boolean
  deprecated?: boolean
  table_name?: string | null
  fields: DocField[]
  title_field?: string
  image_field?: string | null
  search_fields?: string[]
  autoname?: string | null
  default_view?: string | null
  quick_filters?: QuickFilter[]
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

/** One row of the DocType `links` table — a related DocType surfaced on the
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

/** One row of the DocType `actions` table — binds a registered action, with
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

// ── Report types ──────────────────────────────────────────────────────────

export interface ReportColumn {
  fieldname: string
  label: string
  fieldtype?: string
}

export type ReportChartType = 'bar' | 'line' | 'area' | 'pie' | 'donut'

export interface ReportChartConfig {
  type: ReportChartType
  /** Column whose values become the category axis / slice labels. */
  label_field: string
  /** One or more numeric columns rendered as series. */
  value_fields: string[]
  stacked?: boolean
  /** Accent for single-series charts; multi-series uses the palette. */
  color?: string
}

export interface ReportSummary {
  /** Doctype identifier (the `grunt_report` PK column — no separate `id`). */
  name: string
  report_name: string
  report_type: string
  doctype?: string | null
  created_at?: string | null
}

export interface ReportDetail extends ReportSummary {
  query?: string | null
  script?: string | null
  columns?: ReportColumn[] | null
  filters_config?: unknown[] | null
  chart_config?: ReportChartConfig | null
}

export interface ReportResult {
  columns: ReportColumn[]
  data: Record<string, unknown>[]
  meta: { rows: number; time_ms: number }
}

// ── User types ────────────────────────────────────────────────────────────

export interface UserPublic {
  id: string
  email: string
  full_name: string
  roles: string[]
  is_superadmin: boolean
  created_at?: string | null
}

export interface GruntDocument {
  /** Synthesized from `name` by the API client shim — use `name` as the canonical PK. */
  id?: string
  name: string
  owner: string
  created_at: string
  modified_at: string
  modified_by: string
  docstatus: 0 | 1 | 2
  [key: string]: unknown
}

export interface PaginationMeta {
  total: number
  page: number
  per_page: number
  pages: number
  /** Opaque cursor for keyset pagination — present when more rows exist */
  next_cursor?: string
}

export interface StandardListResponse<T> {
  success: boolean
  data: T[]
  meta: PaginationMeta
}

export interface StandardResponse<T> {
  success: boolean
  data: T
}

export interface ApiError {
  success: false
  error: { code: string; message: string; details: string[] }
}

// ── Dashboard ─────────────────────────────────────────────────────────────

export type WidgetType = 'metric' | 'gauge' | 'chart_area' | 'chart_bar' | 'donut' | 'list'
  | 'shortcut' | 'shortcuts_grid' | 'text' | 'clock' | 'activity'
  | 'calendar' | 'heatmap' | 'funnel' | 'table' | 'links'
export type WidgetAggregation = 'count' | 'sum' | 'avg' | 'min' | 'max'
export type WidgetPeriod = '7d' | '30d' | '90d' | '365d'
export type WidgetCols = 1 | 2 | 3 | 4

export type LinkType = 'DocType' | 'Report' | 'Page' | 'URL'

export interface ShortcutItem {
  title: string
  icon?: string | null
  link_type: LinkType
  link_to: string
  color?: string
}

export interface DashboardWidget {
  id: string
  dashboard_id?: string
  widget_type: WidgetType
  title: string
  doctype: string
  field?: string | null
  aggregation: WidgetAggregation
  group_by?: string | null
  date_field?: string | null
  period: WidgetPeriod
  filters?: Record<string, string>
  min_value?: number | null
  max_value?: number | null
  cols: WidgetCols
  color: string
  icon?: string | null
  link_type?: LinkType | null
  description?: string | null
  /** For chart_bar/chart_area/donut: draw data from this saved Report (report_name) instead of a doctype aggregate. */
  report?: string | null
  content?: string | null
  sequence: number
}

export interface Dashboard {
  id: string
  name: string
  label: string
  description: string
  workspace?: string | null
  roles: string
  is_published: boolean
  created_at?: string
  modified_at?: string
  widgets: DashboardWidget[]
}

export interface Page {
  name: string
  label: string
  description?: string | null
  is_published: boolean
  roles: string
  created_at?: string
  modified_at?: string
  widgets: DashboardWidget[]
}

export interface PageSummary extends Omit<Page, 'widgets'> { }

// ── Notifications ────────────────────────────────────────────────────────

export interface GruntNotification {
  id: string
  subject: string
  message: string
  doctype?: string | null
  doc_id?: string | null
  is_read: boolean
  created_at: string | null
}

export type RealtimeMessageType = 'success' | 'error' | 'info' | 'warning'

export interface RealtimeEvent {
  event: string
  data: {
    message?: string
    type?: RealtimeMessageType
    subject?: string
    doctype?: string
    doc_id?: string
    [key: string]: unknown
  }
}
