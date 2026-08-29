import { ChartGantt } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'
import type { DocType, DocField, ActiveFilter } from '@/types'

const SYSTEM_DATE_FIELDS = new Set(['created_at', 'modified_at'])

const def: ViewDefinition = {
  type: 'gantt',
  label: 'Діаграма Ганта',
  icon: ChartGantt,
  order: 4,

  // Enabled once a start field is configured, or auto-detected: needs at least
  // two Date/Datetime fields (start + end) to draw a bar.
  resolveField: (dt: DocType): DocField | null => {
    const configured = dt.gantt_view?.start_field
    if (configured && SYSTEM_DATE_FIELDS.has(configured)) {
      return { fieldname: configured, fieldtype: 'Datetime', label: configured } as DocField
    }
    if (configured) {
      return dt.fields.find((f) => f.fieldname === configured) ?? null
    }
    const dateFields = dt.fields.filter((f) => f.fieldtype === 'Date' || f.fieldtype === 'Datetime')
    return dateFields.length >= 2 ? dateFields[0] : null
  },

  component: () => import('./GanttView.vue').then((m) => m.default),
  settingsComponent: () => import('./GanttSettings.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    doctype: ctx.dt,
    workspace: ctx.workspace,
    activeFilters: ctx.activeFilters,
    fastFilterValues: ctx.fastFilterValues,
    refreshKey: ctx.refreshKey,
  }),

  mountEvents: (ctx) => ({
    'onUpdate:activeFilters': (val: unknown) =>
      ctx.emit.updateActiveFilters(val as ActiveFilter[]),
  }),
}

export default def
