import { N_ } from '@/plugins/i18n'
import { FolderOpen } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'

const def: ViewDefinition = {
  type: 'explorer',
  label: N_('Explorer'),
  icon: FolderOpen,
  order: 5,
  // The personal file spaces (File, browsed by its FileFolder tree) in the same
  // Explorer as the attach picker. It shows its own folders and fetches its own
  // data, so the list's tree panel and pager step aside.
  managesOwnScroll: true,

  resolveField: (dt) => {
    const field = dt.list_tree_field ? dt.fields.find((f) => f.fieldname === dt.list_tree_field) : null
    return field?.fieldtype === 'Link' && field.options === 'FileFolder' ? field : null
  },

  component: () => import('./ExplorerView.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    doctype: ctx.doctype,
    workspace: ctx.workspace,
    refreshKey: ctx.refreshKey,
  }),
}

export default def
