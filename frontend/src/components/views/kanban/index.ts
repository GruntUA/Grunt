import { LayoutGrid } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'
import type { DocType, DocField } from '@/types'

const def: ViewDefinition = {
  type: 'kanban',
  label: 'Канбан',
  icon: LayoutGrid,
  order: 1,

  resolveField: (dt: DocType): DocField | null =>
    dt.fields.find((f) => f.fieldtype === 'Select' && f.in_list_view && !f.hidden) ?? null,

  component: () => import('./KanbanView.vue').then((m) => m.default),
  settingsComponent: () => import('./KanbanSettings.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    doctype: ctx.dt,
    columnField: ctx.resolvedField?.fieldname ?? '',
  }),
}

export default def
