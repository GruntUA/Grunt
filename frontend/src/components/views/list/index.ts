import { LayoutList } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'

const def: ViewDefinition = {
  type: 'list',
  label: 'List',
  icon: LayoutList,
  order: 0,
  fillsViewport: true,

  // No resolveField — list is always available

  component: () => import('./ListTableView.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    dt: ctx.dt,
    workspace: ctx.workspace,
    doctype: ctx.doctype,
    rows: ctx.rows,
    columns: ctx.columns,
    fields: ctx.fields,
    meta: ctx.meta,
    isLoading: ctx.isLoading && !ctx.hasData,
    sortKey: ctx.sortKey,
    sortOrder: ctx.sortOrder,
    groupBy: ctx.groupBy,
    groupedRows: ctx.groupedRows,
    collapsedGroups: ctx.collapsedGroups,
    groupByField: ctx.groupByField,
    selection: ctx.selection,
    isSystemManager: ctx.isSystemManager,
  }),

  mountEvents: (ctx) => ({
    onSort: (key: unknown) => ctx.emit.sort(key as string),
    onRowClick: (row: unknown) => ctx.emit.rowClick(row as Record<string, unknown>),
    onInlineUpdate: (rowId: unknown, field: unknown, value: unknown) =>
      ctx.emit.inlineUpdate(rowId as string, field as string, value as string),
    onDelete: (replaceWith: unknown) => ctx.emit.delete(replaceWith as string | undefined),
    onFastDelete: () => ctx.emit.fastDelete(),
    onClear: () => ctx.emit.clear(),
    onSelectAll: () => ctx.emit.selectAll(),
    onUpdate: (field: unknown, value: unknown) =>
      ctx.emit.update(field as string, value),
    onToggleGroup: (key: unknown) => ctx.emit.toggleGroup(key as string),
  }),

  // ── Toolbar controls (columns, grouping, sorting) ──────────────────────────

  toolbarControls: () => import('./ListToolbarControls.vue').then((m) => m.default),

  mountToolbarProps: (ctx) => ({
    columns: ctx.extras.columns,
    groupableFields: ctx.extras.groupableFields,
    groupBy: ctx.extras.groupBy,
    groupByField: ctx.extras.groupByField,
    sortKey: ctx.extras.sortKey,
    sortOrder: ctx.extras.sortOrder,
    sortableColumns: ctx.extras.sortableColumns,
  }),

  mountToolbarEvents: (ctx) => ({
    'onUpdate:groupBy': (val: unknown) => ctx.emit.updateGroupBy(val as string | null),
    onSort: (key: unknown) => ctx.emit.sort(key as string),
  }),
}

export default def
