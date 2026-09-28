import { Map as MapIcon } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'
import type { DocType, DocField, ScriptMenuItem } from '@/types'

const def: ViewDefinition = {
  type: 'map',
  label: 'Map',
  icon: MapIcon,
  order: 5,

  resolveField: (dt: DocType): DocField | null => {
    const configured = dt.map_view?.geo_field
    if (configured) {
      return dt.fields.find((f) => f.fieldname === configured) ?? null
    }
    return dt.fields.find((f) => f.fieldtype === 'Geolocation' && f.in_list_view && !f.hidden) ?? null
  },

  component: () => import('./MapView.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    doctype: ctx.dt,
    geoField: ctx.resolvedField?.fieldname ?? '',
    workspace: ctx.workspace,
    search: ctx.search,
    filters: ctx.activeFilters,
  }),

  mountEvents: (ctx) => ({
    onRegisterMenuItems: (items: unknown) =>
      ctx.emit.registerMenuItems(items as ScriptMenuItem[]),
    onUnregisterMenuItems: (items: unknown) =>
      ctx.emit.unregisterMenuItems(items as ScriptMenuItem[]),
  }),
}

export default def
