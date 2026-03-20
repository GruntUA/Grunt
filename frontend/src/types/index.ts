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
  columns?: 1 | 2 | 3 | 4
  collapsible?: boolean
  min_value?: number
  max_value?: number
}

export interface DocTypeSummary {
  name: string
  label: string
  module: string
  is_child?: boolean
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

export interface WorkflowDef {
  state_field: string
  states: WorkflowState[]
  transitions: WorkflowTransition[]
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
}

// ── DocType ───────────────────────────────────────────────────────────────

export interface DocType {
  name: string
  label: string
  module: string
  is_child?: boolean
  is_submittable?: boolean
  fields: DocField[]
  title_field?: string
  search_fields?: string[]
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
