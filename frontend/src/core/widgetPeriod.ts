import { computed, ref, type InjectionKey } from 'vue'
import type { DashboardWidget, DocField, WidgetPeriod } from '@/types'
import { parseSelectOptions } from '@/lib/selectOptions'
import { useDocTypeStore } from '@/stores/doctype'

/** Recomputes one widget for another period - provided by the page that renders
 *  the widgets; a widget without it (e.g. the editor preview) shows no switcher. */
export type WidgetPeriodLoader = (widget: DashboardWidget, period: WidgetPeriod) => Promise<unknown>

export const WIDGET_PERIOD_LOADER: InjectionKey<WidgetPeriodLoader> = Symbol('widgetPeriodLoader')

/** Period choices with captions - the options of PageWidget.period (translatable Select). */
export function useWidgetPeriods() {
  const field = ref<DocField | null>(null)
  useDocTypeStore().get('PageWidget')
    .then((dt) => { field.value = dt.fields?.find(f => f.fieldname === 'period') ?? null })
    .catch(() => { /* no options - no switcher */ })
  return computed(() => parseSelectOptions(field.value?.options, field.value?.option_labels))
}
