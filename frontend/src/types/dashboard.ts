/** Dashboard pages and widgets. */

export type WidgetAggregation = 'count' | 'sum' | 'avg' | 'min' | 'max'

/** One of the options of PageWidget.period (7d, 30d, ..., all). */
export type WidgetPeriod = string

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
  /** A registered widget type (core or an app's) - see core/widgetRegistry. */
  widget_type: string
  title: string
  ref_doctype: string
  field?: string | null
  aggregation: WidgetAggregation
  group_by?: string | null
  date_field?: string | null
  period: WidgetPeriod
  /** table: viewers can switch the period on the widget itself. */
  period_switch?: boolean | number
  filters?: Record<string, string>
  min_value?: number | null
  max_value?: number | null
  cols: WidgetCols
  color: string
  icon?: string | null
  link_type?: LinkType | null
  description?: string | null
  /** table: heading of the value column instead of the aggregation name. */
  value_label?: string | null
  /** table: how many rows to show (default 20). */
  row_limit?: number | null
  /** For chart_bar/chart_area/donut: draw data from this saved Report (report_name) instead of a doctype aggregate. */
  report?: string | null
  content?: string | null
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
