import { inject, type InjectionKey, type Ref } from 'vue'
import type { DashboardWidget } from '@/types'

export const WIDGET_FIELD_KEY: InjectionKey<Ref<DashboardWidget>> = Symbol('widgetField')
export const WIDGET_UPDATE_KEY: InjectionKey<(key: string, val: unknown) => void> = Symbol('widgetUpdate')

/** Used inside widget config-section components to access the selected widget and updater. */
export function useWidgetPropertyEditor() {
  const widget = inject(WIDGET_FIELD_KEY)!
  const updateWidget = inject(WIDGET_UPDATE_KEY)!
  return { widget, updateWidget }
}
