import { CalendarDays } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'
import type { DocType, DocField } from '@/types'

const def: ViewDefinition = {
  type: 'calendar',
  label: 'Calendar',
  icon: CalendarDays,
  order: 2,
  // Calendar fetches its own month window and scrolls its grid internally -
  // it doesn't use the shared list pager.
  managesOwnScroll: true,

  resolveField: (dt: DocType): DocField | null => {
    const configured = dt.calendar_date_field
    if (configured && new Set(['created_at', 'modified_at']).has(configured)) {
      return { fieldname: configured, fieldtype: 'Datetime', label: configured } as DocField
    }
    if (configured) {
      return dt.fields.find((f) => f.fieldname === configured) ?? null
    }
    return dt.fields.find((f) => f.fieldtype === 'Date' || f.fieldtype === 'Datetime') ?? null
  },

  component: () => import('./CalendarView.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    doctype: ctx.dt,
    dateField: ctx.resolvedField?.fieldname ?? '',
    workspace: ctx.workspace,
    refreshKey: ctx.refreshKey,
  }),
}

export default def
