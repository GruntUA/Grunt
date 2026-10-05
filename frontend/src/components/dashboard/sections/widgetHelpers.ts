import type { DashboardWidget } from '@/types'

/** Shared color swatch palette - used by the widget-level Color section and per-tile pickers. */
export const WIDGET_COLORS: { value: string; bg: string }[] = [
  { value: 'primary', bg: '#2D6A4F' },
  { value: 'blue',    bg: '#3b82f6' },
  { value: 'amber',   bg: '#f59e0b' },
  { value: 'red',     bg: '#ef4444' },
  { value: 'violet',  bg: '#8b5cf6' },
  { value: 'cyan',    bg: '#06b6d4' },
]

/** i18n keys for WIDGET_COLORS' human-readable names (swatch title tooltip). */
export const WIDGET_COLOR_LABEL_KEYS: Record<string, string> = {
  primary: 'Green',
  blue: 'Blue',
  amber: 'Yellow',
  red: 'Red',
  violet: 'Violet',
  cyan: 'Cyan',
}

/** chart_area / chart_bar / donut can draw data from a saved Report instead of a doctype aggregate. */
export function supportsReportSource(w: DashboardWidget): boolean {
  return w.widget_type === 'chart_area' || w.widget_type === 'chart_bar' || w.widget_type === 'donut'
}

/** `report == null` -> doctype-aggregate source; `report === ''` -> report source, none picked yet. */
export function isReportSourced(w: DashboardWidget): boolean {
  return supportsReportSource(w) && w.report != null
}
