/**
 * `frm.dashboard` - the area above a document form that client scripts fill
 * with a headline, stat indicators, progress bars, a chart, a heatmap, custom
 * HTML sections, related document transactions and connection badge counts.
 *
 * The state is reactive and mutated directly by the API, so calls made outside
 * an event handler (a button, a `grunt.call` callback) show up immediately.
 * The form resets it before every `on_load`; `permanent` comments and headlines survive.
 *
 * ```js
 * grunt.ui.form.on('Invoice', {
 *   on_load(frm) {
 *     if (frm.doc.outstanding > 0) frm.dashboard.set_headline('Не оплачено', 'red')
 *     frm.dashboard.add_indicator(`Сума: ${frm.doc.total}`, 'green')
 *     frm.dashboard.add_progress('Оплата', frm.doc.paid / frm.doc.total * 100)
 *   },
 * })
 * ```
 */

import { reactive, type InjectionKey } from 'vue'

export interface DashboardIndicator {
  label: string
  color: string
}

export interface DashboardProgressSegment {
  title?: string
  /** 0-100 share of the bar. */
  width: number
  color?: string
}

export interface DashboardProgress {
  title: string
  segments: DashboardProgressSegment[]
  message?: string
}

export interface DashboardGraph {
  title?: string
  type: 'line' | 'bar' | 'area'
  labels: string[]
  datasets: { name: string; values: number[] }[]
  colors?: string[]
  /** ISO code (`UAH`) - values shown as money: `125 тис.` on the axis, `125 000,00 ₴` in tooltips. */
  currency?: string | null
  /** Chart height in px (default: proportional to the width). */
  height?: number
}

export interface DashboardHeatmap {
  title?: string
  entries: { date: string; count: number }[]
  /** Days the grid covers, ending today. */
  days: number
}

export interface DashboardSection {
  name: string
  label?: string
  html: string
  css_class?: string
  hidden: boolean
}

export interface DashboardComment {
  html: string
  color: string
  permanent: boolean
}

export interface DashboardBadge {
  open_count?: number
  count?: number
}

export interface DashboardTransactionGroup {
  label?: string
  items: string[]
}

export interface FormDashboardState {
  hidden: boolean
  headline: { html: string; color: string; permanent?: boolean } | null
  indicators: DashboardIndicator[]
  progress: DashboardProgress[]
  graph: DashboardGraph | null
  heatmap: DashboardHeatmap | null
  sections: DashboardSection[]
  comments: DashboardComment[]
  transactions: DashboardTransactionGroup[]
  docstatus_icon: string | null
  /** Overrides of the "Зв'язки" chip counts, keyed by link_doctype. */
  badges: Record<string, DashboardBadge>
}

/** Chart/heatmap arguments accepted by render_graph / render_heatmap. */
export interface GraphArgs {
  title?: string
  type?: 'line' | 'bar' | 'area'
  colors?: string[]
  /** ISO currency code: format values as money (`125 000,00 ₴`). */
  currency?: string
  /** Chart height in px. */
  height?: number
  data: { labels: string[]; datasets: { name?: string; values: number[] }[] }
}

export interface HeatmapArgs {
  title?: string
  data: {
    /** `{ <unix seconds | YYYY-MM-DD>: count }` */
    dataPoints: Record<string, number>
    start?: Date | string
    end?: Date | string
  }
}

export interface TransactionArgs {
  label?: string
  items: string[]
}

export interface FormDashboardApi {
  readonly state: FormDashboardState
  /** A banner across the top of the form; `color` is an indicator colour (red, green, …). */
  set_headline: (html: string, color?: string, permanent?: boolean) => void
  set_headline_alert: (html: string, color?: string, permanent?: boolean) => void
  clear_headline: () => void
  /** A coloured stat badge, e.g. `add_indicator('Оплачено: 12 000 ₴', 'green')`. */
  add_indicator: (label: string, color?: string) => void
  /**
   * A progress bar: `percent` is 0-100, or a list of coloured segments.
   * A second call with the same title replaces the bar.
   */
  add_progress: (
    title: string,
    percent: number | { title?: string; width: number; progress_class?: string; color?: string }[],
    message?: string,
  ) => void
  show_progress: FormDashboardApi['add_progress']
  render_graph: (args: GraphArgs) => void
  render_heatmap: (args: HeatmapArgs) => void
  /** Related documents / transaction shortcuts in the dashboard. */
  add_transactions: (opts: TransactionArgs) => void
  /** Raw HTML block; returns its name for clear_section. */
  add_section: (html: string, label?: string, css_class?: string, hidden?: boolean) => string
  clear_section: (name: string) => void
  /** Override the count (and "open" count) shown on a "Зв'язки" chip. */
  set_badge_count: (link_doctype: string, open_count?: number, count?: number) => void
  set_badge_count_for_external_link: FormDashboardApi['set_badge_count']
  /** Status indicator icon / label (Draft, Submitted, Cancelled). */
  set_docstatus_icon: (status: string | number) => void
  /** An alert line; `permanent` keeps it across reset(). */
  add_comment: (html: string, color?: string, permanent?: boolean) => void
  clear_comment: () => void
  show: () => void
  hide: () => void
  /** Clear everything except permanent items. */
  reset: () => void
}

/** Lets DocConnections read badge overrides without threading props through FormRenderer. */
export const FORM_DASHBOARD: InjectionKey<FormDashboardState> = Symbol('formDashboard')

// Standard progress classes -> indicator colours
const PROGRESS_CLASS_COLOR: Record<string, string> = {
  'progress-bar-success': 'green',
  'progress-bar-warning': 'orange',
  'progress-bar-danger': 'red',
  'progress-bar-info': 'blue',
}

// Standard alert classes -> indicator colours
const ALERT_CLASS_COLOR: Record<string, string> = {
  'alert-success': 'green',
  'alert-warning': 'orange',
  'alert-danger': 'red',
  'alert-info': 'blue',
}

const clamp = (n: number) => Math.max(0, Math.min(100, Number(n) || 0))

function dayKey(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** `1697232000` (unix seconds), `'1697232000'` or `'2026-10-14'` -> `YYYY-MM-DD`. */
function pointDay(key: string): string {
  return /^\d+$/.test(key) ? dayKey(new Date(Number(key) * 1000)) : key.slice(0, 10)
}

function emptyState(): FormDashboardState {
  return {
    hidden: false,
    headline: null,
    indicators: [],
    progress: [],
    graph: null,
    heatmap: null,
    sections: [],
    comments: [],
    transactions: [],
    docstatus_icon: null,
    badges: {},
  }
}

export function createFormDashboard(): FormDashboardApi {
  const state = reactive(emptyState()) as FormDashboardState
  let sectionSeq = 0

  const api: FormDashboardApi = {
    state,

    set_headline(html, color = 'blue', permanent = false) {
      const resolvedColor = ALERT_CLASS_COLOR[color] || color
      state.headline = { html, color: resolvedColor, permanent }
    },
    set_headline_alert(html, color = 'blue', permanent = false) {
      api.set_headline(html, color, permanent)
    },
    clear_headline() {
      state.headline = null
    },

    add_indicator(label, color = 'gray') {
      state.indicators.push({ label, color })
    },

    add_progress(title, percent, message) {
      const segments: DashboardProgressSegment[] = Array.isArray(percent)
        ? percent.map((s) => ({
          title: s.title,
          width: clamp(s.width),
          color: s.color ?? PROGRESS_CLASS_COLOR[s.progress_class ?? ''],
        }))
        : [{ width: clamp(percent) }]
      const bar = { title, segments, message }
      const i = state.progress.findIndex((p) => p.title === title)
      if (i >= 0) state.progress[i] = bar
      else state.progress.push(bar)
    },
    show_progress(title, percent, message) {
      api.add_progress(title, percent, message)
    },

    render_graph(args) {
      const datasets = args.data?.datasets ?? []
      state.graph = {
        title: args.title,
        type: args.type ?? 'line',
        colors: args.colors,
        currency: args.currency ?? null,
        height: args.height,
        labels: (args.data?.labels ?? []).map(String),
        datasets: datasets.map((d, i) => ({ name: d.name || String(i + 1), values: d.values.map(Number) })),
      }
    },

    render_heatmap(args) {
      const totals = new Map<string, number>()
      for (const [key, count] of Object.entries(args.data?.dataPoints ?? {})) {
        const day = pointDay(key)
        totals.set(day, (totals.get(day) ?? 0) + Number(count))
      }
      const start = args.data?.start ? new Date(args.data.start) : null
      const days = start ? Math.ceil((Date.now() - start.getTime()) / 86_400_000) : 365
      state.heatmap = {
        title: args.title,
        entries: [...totals].map(([date, count]) => ({ date, count })),
        days: Math.max(7, Math.min(365, days)),
      }
    },

    add_transactions(opts) {
      if (opts && Array.isArray(opts.items)) {
        state.transactions.push({
          label: opts.label || '',
          items: [...opts.items],
        })
      }
    },

    add_section(html, label, css_class, hidden = false) {
      const name = `section-${++sectionSeq}`
      state.sections.push({ name, html, label, css_class, hidden })
      return name
    },
    clear_section(name) {
      const lower = name.toLowerCase()
      if (lower === 'chart' || lower === 'graph') {
        state.graph = null
      } else if (lower === 'heatmap') {
        state.heatmap = null
      } else if (lower === 'progress') {
        state.progress = []
      } else if (lower === 'transactions' || lower === 'connections') {
        state.transactions = []
      } else if (lower === 'indicators') {
        state.indicators = []
      } else {
        state.sections = state.sections.filter((s) => s.name !== name && s.label !== name)
      }
    },

    set_badge_count(link_doctype, open_count, count) {
      state.badges[link_doctype] = { open_count, count }
    },
    set_badge_count_for_external_link(link_doctype, open_count, count) {
      api.set_badge_count(link_doctype, open_count, count)
    },

    set_docstatus_icon(status) {
      if (typeof status === 'number') {
        if (status === 0) state.docstatus_icon = 'Draft'
        else if (status === 1) state.docstatus_icon = 'Submitted'
        else if (status === 2) state.docstatus_icon = 'Cancelled'
        else state.docstatus_icon = String(status)
      } else {
        state.docstatus_icon = status ? String(status) : null
      }
    },

    add_comment(html, color = 'blue', permanent = false) {
      const resolvedColor = ALERT_CLASS_COLOR[color] || color
      state.comments.push({ html, color: resolvedColor, permanent })
    },
    clear_comment() {
      state.comments = []
    },

    show() {
      state.hidden = false
    },
    hide() {
      state.hidden = true
    },

    reset() {
      const permanentHeadline = state.headline?.permanent ? state.headline : null
      const permanentComments = state.comments.filter((c) => c.permanent)
      Object.assign(state, emptyState(), {
        headline: permanentHeadline,
        comments: permanentComments,
      })
    },
  }
  return api
}

/** Nothing for the area to show (hidden areas count as empty). */
export function isDashboardEmpty(s: FormDashboardState): boolean {
  if (!s || s.hidden) return true
  return (
    !s.headline &&
    !s.indicators.length &&
    !s.progress.length &&
    !s.graph &&
    !s.heatmap &&
    !s.sections.some((x) => !x.hidden) &&
    !s.comments.length &&
    !s.transactions.length &&
    !s.docstatus_icon
  )
}
