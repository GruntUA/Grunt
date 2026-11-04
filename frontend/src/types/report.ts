/** Saved reports and their results. */

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
}

export interface ReportResult {
  columns: ReportColumn[]
  data: Record<string, unknown>[]
  meta: { rows: number; time_ms: number }
}
