import { N_ } from '@/plugins/i18n'
import { ShieldCheck } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'

/**
 * The permission matrix of the DocType list: one role's rules on the listed
 * DocTypes, actions as columns (PERMISSIONS_PLAN, step 2d). Rows are the list's
 * own page - its filters (module, app, search) pick the DocTypes.
 */
const def: ViewDefinition = {
  type: 'permissions',
  label: N_('Permissions'),
  icon: ShieldCheck,
  order: 20,
  fillsViewport: true,

  available: (dt) => dt.name === 'DocType',

  component: () => import('./PermissionMatrixView.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    rows: ctx.rows,
    workspace: ctx.workspace,
    isLoading: ctx.isLoading && !ctx.hasData,
    refreshKey: ctx.refreshKey,
  }),
}

export default def
