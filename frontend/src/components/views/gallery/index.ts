import { Image as ImageIcon } from '@lucide/vue'
import type { ViewDefinition } from '@/core/viewRegistry'

const def: ViewDefinition = {
  type: 'gallery',
  label: 'Галерея',
  icon: ImageIcon,
  order: 4,

  // No resolveField — gallery is always available

  component: () => import('./GalleryViewWrapper.vue').then((m) => m.default),

  mountProps: (ctx) => ({
    rows: ctx.rows,
    columns: ctx.columns,
    fields: ctx.fields,
    doctype: ctx.doctype,
    imageField: ctx.imageField,
    workspace: ctx.workspace,
    isLoading: ctx.isLoading && !ctx.hasData,
    selectionCount: ctx.selectionCount,
    selection: {
      selectedIds: ctx.selection.selectedIds,
      allSelected: ctx.selection.allSelected,
      isSelected: ctx.selection.isSelected,
      toggle: ctx.selection.toggle,
    },
    editableFields: ctx.dt?.fields,
    meta: ctx.meta,
  }),

  mountEvents: (ctx) => ({
    onDelete: () => ctx.emit.delete(),
    onClear: () => ctx.emit.clear(),
    onSelectAll: () => ctx.emit.selectAll(),
    onUpdate: (field: unknown, value: unknown) =>
      ctx.emit.update(field as string, value),
    'onUpdate:page': (page: unknown) => ctx.emit.page(page as number),
  }),
}

export default def
