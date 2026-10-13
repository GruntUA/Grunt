<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, inject, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { DashboardWidget, WidgetPeriod } from '@/types'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { WIDGET_PERIOD_LOADER, useWidgetPeriods } from '@/core/widgetPeriod'
import { docUrl } from '@/core/workspaceUrl'
import { filteredListUrl, groupFilter } from '@/pages/reports/drilldown'
import { Progress } from '@/components/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const { t } = useI18n()

interface Row {
  label: string
  value: number
  /** Raw group value (null for the "-" bucket). */
  key?: unknown
  /** Document id when the group is exactly one row. */
  doc?: string | null
}

interface TableData {
  rows: Row[]
  aggregation?: string
  field?: string | null
  group_label?: string | null
  value_label?: string | null
  link_doctype?: string | null
  filters?: Record<string, unknown>
}

const props = defineProps<{
  widget: DashboardWidget
  data: TableData | null
  loading?: boolean
  workspaceName?: string
}>()

const router = useRouter()

// Period switcher: the page's data is for the configured period; any other
// period is fetched for this widget alone.
const loadPeriod = inject(WIDGET_PERIOD_LOADER, null)
const PERIODS = useWidgetPeriods()
const showSwitch = computed(() =>
  !!props.widget.period_switch && !!props.widget.date_field && !!loadPeriod && PERIODS.value.length > 0)
const period = ref<WidgetPeriod>(props.widget.period)
const periodData = ref<TableData | null>(null)
const switching = ref(false)
let periodSeq = 0

async function fetchPeriod(p: WidgetPeriod) {
  const seq = ++periodSeq // a quick re-click must not show the previous period's answer
  if (p === props.widget.period || !loadPeriod) {
    periodData.value = null
    switching.value = false
    return
  }
  switching.value = true
  try {
    const result = await loadPeriod(props.widget, p) as TableData | null
    if (seq === periodSeq) periodData.value = result ?? { rows: [] }
  } catch { /* keep the rows shown */ } finally {
    if (seq === periodSeq) switching.value = false
  }
}

function selectPeriod(p: unknown) {
  if (!p || p === period.value) return
  period.value = p as WidgetPeriod
  void fetchPeriod(period.value)
}

// A page refresh brings fresh data for the configured period only.
watch(() => props.data, () => { if (period.value !== props.widget.period) void fetchPeriod(period.value) })

const tableData = computed(() => periodData.value ?? props.data)
const rows = computed(() => tableData.value?.rows ?? [])
const maxValue = computed(() => Math.max(...rows.value.map(r => r.value), 1))

const aggLabel = computed(() => {
  const map: Record<string, string> = {
    count: t('Count'), sum: t('Sum'), avg: t('Average'), min: t('Min'), max: t('Max'),
  }
  return map[tableData.value?.aggregation ?? 'count'] ?? t('Value')
})

function barWidth(value: number): number {
  return Math.max(4, Math.round((value / maxValue.value) * 100))
}

/** Single-row group -> that document; Link group -> the linked record; else the filtered list. */
function open(row: Row) {
  const { widget } = props
  const data = tableData.value
  if (row.doc) return router.push(docUrl(widget.ref_doctype, row.doc))
  const isNull = row.key === null || row.key === undefined
  if (data?.link_doctype && !isNull) return router.push(docUrl(data.link_doctype, row.key))
  if (!widget.group_by || !data?.filters) return
  router.push(filteredListUrl(
    widget.ref_doctype, { ...data.filters, ...groupFilter(widget.group_by, row.key) }, props.workspaceName,
  ))
}

function formatVal(v: number): string {
  return v % 1 === 0 ? String(v) : v.toFixed(1)
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Header -->
    <div class="px-4 pt-3 pb-2 shrink-0 flex flex-wrap items-start justify-between gap-2">
      <div class="min-w-0">
        <p class="font-medium text-muted-foreground">{{ widget.title }}</p>
        <p v-if="widget.description" class="text-muted-foreground/80">{{ widget.description }}</p>
      </div>
      <ToggleGroup v-if="showSwitch" type="single" variant="outline" size="sm"
        :model-value="period" @update:model-value="selectPeriod">
        <ToggleGroupItem v-for="p in PERIODS" :key="p.value" :value="p.value" class="px-2.5">{{ p.label }}</ToggleGroupItem>
      </ToggleGroup>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="flex-1 px-4 flex flex-col gap-1.5 py-1">
      <div v-for="i in 5" :key="i" class="h-6 bg-muted animate-pulse rounded" />
    </div>

    <!-- Empty -->
    <div v-else-if="rows.length === 0"
      class="flex-1 flex items-center justify-center text-muted-foreground">
      {{ t('No data') }}
    </div>

    <!-- Table -->
    <div v-else :class="['flex-1 overflow-auto transition-opacity', switching && 'opacity-50']">
      <Table class="table-fixed">
        <TableHeader class="sticky top-0 bg-card">
          <TableRow>
            <TableHead>{{ tableData?.group_label || widget.group_by || t('Group') }}</TableHead>
            <TableHead class="w-24 text-right">{{ widget.value_label || tableData?.value_label || aggLabel }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="row in rows" :key="row.label" class="cursor-pointer" @click="open(row)">
            <TableCell>
              <div class="flex items-center gap-2">
                <Progress :model-value="barWidth(row.value)" class="h-1.5 w-20 shrink-0" />
                <span class="min-w-0 truncate" :title="row.label">{{ row.label }}</span>
              </div>
            </TableCell>
            <TableCell class="text-right font-semibold tabular-nums">{{ formatVal(row.value) }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>
