<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { Doughnut } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import type { ActiveElement, ChartEvent } from 'chart.js'
import type { DashboardWidget } from '@/types'
import { filteredListUrl, groupFilter } from '@/pages/reports/drilldown'

ChartJS.register(ArcElement, Tooltip, Legend)

const { t } = useI18n()

const props = defineProps<{
  widget: DashboardWidget
  data: { labels: string[]; values: number[]; keys?: unknown[]; filters?: Record<string, unknown> } | null
  loading?: boolean
  workspaceName?: string
}>()

const router = useRouter()

// Report-sourced donuts carry no `keys`/`filters` and stay non-clickable.
const canOpen = computed(() => !!props.widget.ref_doctype && !!props.widget.group_by && !!props.data?.keys)

/** Segment -> the widget's list filtered to that group. */
function onClick(_e: ChartEvent, els: ActiveElement[]) {
  const { widget, data } = props
  if (!canOpen.value || !els.length) return
  router.push(filteredListUrl(
    widget.ref_doctype,
    { ...data!.filters, ...groupFilter(widget.group_by!, data!.keys![els[0].index]) },
    props.workspaceName,
  ))
}

function onHover(e: ChartEvent, els: ActiveElement[]) {
  const canvas = e.native?.target as HTMLElement | undefined
  if (canvas) canvas.style.cursor = canOpen.value && els.length ? 'pointer' : 'default'
}

const PALETTE = [
  '#2D6A4F', '#3b82f6', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#10b981', '#f97316',
]

const total = computed(() => props.data?.values.reduce((a, b) => a + b, 0) ?? 0)

const chartData = computed(() => ({
  labels: props.data?.labels ?? [],
  datasets: [{
    data: props.data?.values ?? [],
    backgroundColor: PALETTE,
    borderWidth: 2,
    borderColor: getComputedStyle(document.documentElement).getPropertyValue('--card').trim() || '#ffffff',
    hoverOffset: 6,
  }],
}))

const chartOptions = {
  onClick,
  onHover,
  responsive: true,
  maintainAspectRatio: false,
  cutout: '68%',
  plugins: {
    legend: {
      position: 'bottom' as const,
      labels: { boxWidth: 10, padding: 12, font: { size: 11 } },
    },
    tooltip: { mode: 'index' as const },
  },
}
</script>

<template>
  <div class="flex flex-col gap-2 p-5 h-full">
    <div class="flex items-start justify-between">
      <p class="text-muted-foreground font-medium">{{ widget.title }}</p>
      <span v-if="total" class="text-muted-foreground tabular-nums">{{ total }} {{ t('total') }}</span>
    </div>

    <div v-if="loading" class="flex-1 bg-muted animate-pulse rounded" />

    <div v-else-if="!data?.labels?.length" class="flex-1 flex items-center justify-center text-muted-foreground">
      {{ t('No data') }}
    </div>

    <div v-else class="flex-1 min-h-0" style="min-height:160px">
      <Doughnut :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
