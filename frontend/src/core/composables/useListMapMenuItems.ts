import type { Ref } from 'vue'
import type { ScriptMenuItem } from '@/types'

export function useListMapMenuItems(listMenuItems: Ref<ScriptMenuItem[]>) {
  function registerMapMenuItems(items: ScriptMenuItem[]) {
    listMenuItems.value.push(...items)
  }

  function unregisterMapMenuItems(items: ScriptMenuItem[]) {
    for (const item of items) {
      const idx = listMenuItems.value.indexOf(item)
      if (idx !== -1) listMenuItems.value.splice(idx, 1)
    }
  }

  return {
    registerMapMenuItems,
    unregisterMapMenuItems,
  }
}