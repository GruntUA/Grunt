import { LayoutGrid } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'
import type { DocType, DocField } from '@/types'

const def: ViewDefinition = {
  type: 'kanban',
  label: 'Канбан',
  icon: LayoutGrid,
  order: 1,
  managesOwnScroll: true,

  resolveField: (dt: DocType): DocField | null => {
    const configured = dt.kanban_column_field
      ? dt.fields.find((f) => f.fieldname === dt.kanban_column_field && f.fieldtype === 'Select')
      : null
    return (
      configured ??
      dt.fields.find((f) => f.fieldtype === 'Select' && f.in_list_view && !f.hidden) ??
      null
    )
  },

  component: () => import('./KanbanView.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    doctype: ctx.dt,
    columnField: ctx.resolvedField?.fieldname ?? '',
    refreshKey: ctx.refreshKey,
  }),
}

export default def
