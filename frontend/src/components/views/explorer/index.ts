import { N_ } from '@/plugins/i18n'
import { FolderOpen } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'
import { hasTrait } from '@/core/fieldRegistry'

const def: ViewDefinition = {
  type: 'explorer',
  label: N_('Explorer'),
  icon: FolderOpen,
  order: 5,
  // The personal file spaces (File, browsed by its FileFolder tree) in the same
  // Explorer as the attach picker. It shows its own folders and fetches its own
  // data, so the list's pager steps aside; it searches on its own, so the
  // list's search and filters step aside too.
  managesOwnScroll: true,
  ownToolbar: true,

  resolveField: (dt) => dt.fields.find((f) => hasTrait(f.fieldtype, 'link') && f.options === 'FileFolder') ?? null,

  component: () => import('./ExplorerView.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    doctype: ctx.doctype,
    workspace: ctx.workspace,
    refreshKey: ctx.refreshKey,
  }),
}

export default def
