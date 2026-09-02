import { Table2 } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'

/**
 * Report view — a dense, Frappe-style "Report" grid over the current list query.
 *
 * Adds on top of the plain list: freely add / remove / reorder columns, an
 * optional single-level group-by with per-group subtotals, a per-column
 * aggregate function (sum / avg / min / max / count), a grand-total row, and
 * a client-side CSV export of the rendered grid. Always available.
 */
const def: ViewDefinition = {
  type: 'report',
  label: 'Звіт',
  icon: Table2,
  order: 6,

  // No resolveField — the report view is always available.

  component: () => import('./ReportGridView.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    dt: ctx.dt,
    workspace: ctx.workspace,
    doctype: ctx.doctype,
    rows: ctx.rows,
    listColumns: ctx.columns,
    fields: ctx.fields,
    activeFilters: ctx.activeFilters,
    meta: ctx.meta,
    isLoading: ctx.isLoading && !ctx.hasData,
    hasData: ctx.hasData,
    sortKey: ctx.sortKey,
    sortOrder: ctx.sortOrder,
    fetchNextPage: ctx.fetchNextPage,
    hasNextPage: ctx.hasNextPage,
    isFetchingNextPage: ctx.isFetchingNextPage,
    refreshKey: ctx.refreshKey,
  }),

  mountEvents: (ctx) => ({
    onSort: (key: unknown) => ctx.emit.sort(key as string),
    onRowClick: (row: unknown) => ctx.emit.rowClick(row as Record<string, unknown>),
  }),
}

export default def
