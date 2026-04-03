export type FieldType =
  | "Text" | "LongText" | "Int" | "Float" | "Check"
  | "Date" | "Datetime" | "Time" | "Select" | "Link"
  | "MultiLink" | "Attach" | "Image" | "RichText"
  | "JSON" | "Code" | "Color" | "Section" | "Column"
  | "Tab" | "Table" | "Signature" | "Geolocation"

export interface DocField {
  fieldname: string
  label: string
  fieldtype: FieldType
  required?: boolean
  unique?: boolean
  read_only?: boolean
  hidden?: boolean
  in_list_view?: boolean
  in_filter?: boolean
  options?: string
  default?: unknown
  description?: string
  placeholder?: string
  depends_on?: string
  columns?: number
  collapsible?: boolean
  min_value?: number
  max_value?: number
}

export interface DocTypeSummary {
  name: string
  label: string
  module: string
  is_child?: boolean
  is_singleton?: boolean
}

// ── Workflow types ────────────────────────────────────────────────────────

export interface WorkflowState {
  name: string
  label: string
  color?: string
  is_initial?: boolean
  is_final?: boolean
}

export interface WorkflowTransition {
  action: string
  from_state: string
  to_state: string
  allowed_roles?: string[]
  condition?: string | null
}

export type WorkflowStepType =
  | 'state' | 'form' | 'approval' | 'notification'
  | 'script' | 'condition' | 'create_doc' | 'stop'

export interface WorkflowStep {
  id: string
  name: string
  title: string
  step_type: WorkflowStepType
  variable?: string | null
  sequence: number
  is_active: boolean
  next_steps: string[]
  config: Record<string, unknown>
}

export interface WorkflowDef {
  state_field: string
  states: WorkflowState[]
  transitions: WorkflowTransition[]
  steps: WorkflowStep[]
  positions?: Record<string, { x: number; y: number }>
}

// ── Permission types ──────────────────────────────────────────────────────

export interface DocTypePermission {
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

export interface DocTypeListView {
  fields: string[]
  sort_by: string
  sort_order: 'asc' | 'desc'
  default_filters: Record<string, string>
}

export interface DocTypeFormView {
  layout: 'standard' | 'compact' | 'wide'
  print_format: string | null
}

export interface DocTypeKanbanView {
  column_field: string
  title_field: string
  color_field: string | null
}

export interface CalendarSource {
  doctype: string
  date_field: string
  end_date_field?: string
  label_field?: string
  color?: string
  filters?: Record<string, string>
  recurring?: boolean
}

export interface DocTypeCalendarView {
  field: string
  end_field?: string
  title_field?: string
  sources?: CalendarSource[]
}

export interface DocTypeTreeView {
  parent_field: string   // fieldname of the self-referential Link field
  title_field?: string   // which field to display as node label (defaults to 'name')
}

// ── Status indicators ────────────────────────────────────────────────────

export interface StatusIndicator {
  value: string
  color: string
  icon?: string | null
  label?: string | null
}

export interface DocTypeStatusConfig {
  field: string
  indicators: StatusIndicator[]
}

// ── DocType ───────────────────────────────────────────────────────────────

export interface DocType {
  name: string
  label: string
  module: string
  is_child?: boolean
  is_submittable?: boolean
  is_singleton?: boolean
  track_changes?: boolean
  fields: DocField[]
  title_field?: string
  image_field?: string | null
  search_fields?: string[]
  autoname?: string | null
  default_view?: 'list' | 'kanban' | 'calendar' | 'tree' | null
  list_view?: DocTypeListView
  form_view?: DocTypeFormView
  kanban_view?: DocTypeKanbanView | null
  calendar_view?: DocTypeCalendarView | null
  tree_view?: DocTypeTreeView | null
  status_config?: DocTypeStatusConfig | null
  workflow?: WorkflowDef | null
  permissions?: DocTypePermission[]
}

// ── Report types ──────────────────────────────────────────────────────────

export interface ReportColumn {
  fieldname: string
  label: string
  fieldtype?: string
}

export interface ReportSummary {
  id: string
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
}

export interface ReportResult {
  columns: ReportColumn[]
  data: Record<string, unknown>[]
  meta: { rows: number; time_ms: number }
}

// ── User types ────────────────────────────────────────────────────────────

export interface GruntUserPublic {
  id: string
  email: string
  full_name: string
  roles: string[]
  is_superadmin: boolean
  created_at?: string | null
}

export interface GruntDocument {
  id: string
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

export type WidgetType = 'metric' | 'chart_area' | 'chart_bar' | 'donut' | 'list'
  | 'shortcut' | 'shortcuts_grid' | 'text' | 'clock' | 'activity'
  | 'calendar' | 'heatmap' | 'funnel' | 'table'
export type WidgetAggregation = 'count' | 'sum' | 'avg' | 'min' | 'max'
export type WidgetPeriod = '7d' | '30d' | '90d' | '365d'
export type WidgetCols = 1 | 2 | 3 | 4

export type LinkType = 'DocType' | 'Report' | 'Dashboard' | 'URL'

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
  cols: WidgetCols
  color: string
  icon?: string | null
  link_type?: LinkType | null
  description?: string | null
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

export interface DashboardSummary extends Omit<Dashboard, 'widgets'> { }

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
