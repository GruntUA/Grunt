/** Saved reports and their results. */

export interface ReportColumn {
  fieldname: string
  label: string
  fieldtype?: string
  /** Summed in the "Total" row. */
  total?: boolean
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
  /** Doctype identifier (the `grunt_report` PK column - no separate `id`). */
  name: string
  report_name: string
  report_type: string
  ref_doctype?: string | null
  created_at?: string | null
}

export interface ReportDetail extends ReportSummary {
  query?: string | null
  script?: string | null
  columns?: ReportColumn[] | null
  filters_config?: unknown[] | null
  chart_config?: ReportChartConfig | null
  /** List reports: always-applied conditions, sort and "top N". */
  conditions?: { fieldname: string; op: string; value?: unknown }[] | null
  sort_by?: string | null
  sort_order?: 'asc' | 'desc' | null
  row_limit?: number | null
  disabled?: boolean | number | null
  roles?: string[] | null
  /** Calculated in the background; the view shows the last saved result. */
  prepared_report?: boolean | number | null
  timeout?: number | null
}

export type PreparedStatus = 'Queued' | 'Started' | 'Completed' | 'Error'

/** State of a prepared report's latest result for the current filters. */
export interface PreparedState {
  status: PreparedStatus | null
  name?: string
  created_at?: string | null
  finished_at?: string | null
  rows?: number | null
  time_ms?: number | null
  error?: string | null
}

export interface ReportResult {
  columns: ReportColumn[]
  data: Record<string, unknown>[]
  meta: { rows: number; time_ms: number }
  /** Set for a prepared report. */
  prepared?: PreparedState
}
