import type { ActionsApi } from '@/core/actions'
import type { ScriptMenuItem } from '@/types'

/** Menu items a list view (e.g. the map) contributes — registered as list actions while it is shown. */
export function useListMapMenuItems(actions: ActionsApi) {
  const id = (item: ScriptMenuItem) => `view:${item.label}`

  function registerMapMenuItems(items: ScriptMenuItem[]) {
    items.forEach((item, index) =>
      actions.add({
        id: id(item),
        label: item.label,
        icon: item.icon,
        placement: 'menu',
        group: 'view',
        order: 50 + index,
        action: () => item.action(),
      }),
    )
  }

  function unregisterMapMenuItems(items: ScriptMenuItem[]) {
    for (const item of items) actions.remove(id(item))
  }

  return { registerMapMenuItems, unregisterMapMenuItems }
}
