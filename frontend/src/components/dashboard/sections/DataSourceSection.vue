<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { reportsApi } from '@/core/api/reports'
import type { ReportSummary } from '@/types'
import { Separator } from '@/components/ui/separator'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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
  <Separator class="!mb-3" />
  <p class="font-semibold text-muted-foreground uppercase tracking-wide mb-3">{{ t('Data source') }}</p>
  <div class="mb-4 flex flex-col gap-2">
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      class="w-full"
      :model-value="isReportSourced(widget) ? 'report' : 'doctype'"
      @update:model-value="(v) => v && setReportSource(v === 'report')"
    >
      <ToggleGroupItem value="doctype" class="flex-1">{{ t('DocType aggregate') }}</ToggleGroupItem>
      <ToggleGroupItem value="report" class="flex-1">{{ t('Saved report') }}</ToggleGroupItem>
    </ToggleGroup>
    <Select
      v-if="isReportSourced(widget)"
      :model-value="widget.report ?? undefined"
      @update:model-value="(v) => updateWidget('report', v ?? '')"
    >
      <SelectTrigger class="w-full">
        <SelectValue :placeholder="t('— Select —')" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="r in reports" :key="r.name" :value="r.report_name">{{ r.report_name }}</SelectItem>
      </SelectContent>
    </Select>
  </div>
</template>
