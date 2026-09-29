import { computed, inject, provide, type InjectionKey, type Ref } from 'vue'

/** dataTransfer type carrying `{ doctype, ids }` of dragged list rows. */
export const ROW_DRAG_MIME = 'application/x-grunt-rows'

interface RowDragContext {
  doctype: string
  /** Rows can be dragged (a drop target — the list's tree panel — is shown). */
  enabled: Ref<boolean>
  selectedIds: Ref<string[]>
}

const ROW_DRAG: InjectionKey<RowDragContext> = Symbol('list-row-drag')

/** DocTypeList: let the list views make their rows draggable. */
export function provideRowDrag(ctx: RowDragContext) {
  provide(ROW_DRAG, ctx)
}

export interface DraggedRows {
  doctype: string
  ids: string[]
}

/** Parse a drop's payload; null when it isn't list rows. */
export function readDraggedRows(e: DragEvent): DraggedRows | null {
  const raw = e.dataTransfer?.getData(ROW_DRAG_MIME)
  if (!raw) return null
  try {
    return JSON.parse(raw) as DraggedRows
  } catch {
    return null
  }
}

/**
 * List views: `draggable` for a row element + its `dragstart` handler.
 * Dragging a selected row carries the whole selection, otherwise just that row.
 */
export function useRowDrag() {
  const ctx = inject(ROW_DRAG, null)
  const draggable = computed(() => !!ctx?.enabled.value)

  function onDragStart(e: DragEvent, rowId: string) {
    if (!ctx || !e.dataTransfer) return
    const selected = ctx.selectedIds.value
    const ids = selected.includes(rowId) ? selected : [rowId]
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData(ROW_DRAG_MIME, JSON.stringify({ doctype: ctx.doctype, ids }))
    e.dataTransfer.setData('text/plain', ids.join(', '))
  }

  return { draggable, onDragStart }
}
