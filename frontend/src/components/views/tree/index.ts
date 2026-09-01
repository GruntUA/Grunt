import { GitBranch } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'
import type { DocType, DocField, ActiveFilter } from '@/types'

const def: ViewDefinition = {
  type: 'tree',
  label: 'Дерево',
  icon: GitBranch,
  order: 3,

  resolveField: (dt: DocType): DocField | null => {
    if (dt.tree_parent_field) {
      return dt.fields.find((f) => f.fieldname === dt.tree_parent_field) ?? null
    }
    return dt.fields.find((f) => f.fieldtype === 'Link' && f.options === dt.name) ?? null
  },

  component: () => import('./TreeView.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    doctype: ctx.dt,
    parentField: ctx.resolvedField?.fieldname ?? '',
    workspace: ctx.workspace,
    fastFilterDefs: ctx.fastFilterDefs,
    fastFilterValues: ctx.fastFilterValues,
    activeFilters: ctx.activeFilters,
    refreshKey: ctx.refreshKey,
  }),

  mountEvents: (ctx) => ({
    'onUpdate:fastFilterValues': (val: unknown) =>
      ctx.emit.updateFastFilterValues(val as Record<string, string>),
    'onUpdate:activeFilters': (val: unknown) =>
      ctx.emit.updateActiveFilters(val as ActiveFilter[]),
  }),
}

export default def
