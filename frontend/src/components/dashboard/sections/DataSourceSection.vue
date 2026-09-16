<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { reportsApi } from '@/core/api/reports'
import type { ReportSummary } from '@/types'
import { useWidgetPropertyEditor } from '@/core/composables/useWidgetPropertyEditor'
import { isReportSourced } from './widgetHelpers'

const { t } = useI18n()
const { widget, updateWidget } = useWidgetPropertyEditor()

const reports = ref<ReportSummary[]>([])
onMounted(async () => {
  try { reports.value = await reportsApi.list() } catch { reports.value = [] }
})

function setReportSource(useReport: boolean) {
  updateWidget('report', useReport ? (widget.value.report ?? '') : null)
}
</script>

<template>
  <div class="space-y-1">
    <label class="font-medium text-muted-foreground uppercase tracking-wide">{{ t('Data source') }}</label>
    <select
      :value="isReportSourced(widget) ? 'report' : 'doctype'"
      class="w-full h-8 px-3 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      @change="setReportSource(($event.target as HTMLSelectElement).value === 'report')"
    >
      <option value="doctype">{{ t('DocType aggregate') }}</option>
      <option value="report">{{ t('Saved report') }}</option>
    </select>
    <select
      v-if="isReportSourced(widget)"
      :value="widget.report"
      class="w-full h-8 px-3 mt-1 rounded-md border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      @change="updateWidget('report', ($event.target as HTMLSelectElement).value)"
    >
      <option value="">{{ t('— Select —') }}</option>
      <option v-for="r in reports" :key="r.name" :value="r.report_name">{{ r.report_name }}</option>
    </select>
  </div>
</template>
