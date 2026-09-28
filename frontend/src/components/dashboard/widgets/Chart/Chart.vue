<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { Bar, Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js'
import type { ActiveElement, ChartEvent, Chart as ChartInstance } from 'chart.js'
import type { DashboardWidget } from '@/types'
import { filteredListUrl, periodRange } from '@/pages/reports/drilldown'

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Filler, Tooltip, Legend)

const { t } = useI18n()

const props = defineProps<{
  widget: DashboardWidget
  data: {
    labels: string[]
    values?: number[]
    groups?: Record<string, number[]>
    filters?: Record<string, unknown>
  } | null
  loading?: boolean
  workspaceName?: string
}>()

const router = useRouter()

const PALETTE = [
  '#2D6A4F', '#3b82f6', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#10b981', '#f97316',
]

const colorAccents: Record<string, string> = {
  primary: '#2D6A4F',
  blue: '#3b82f6',
  green: '#10b981',
  amber: '#f59e0b',
  red: '#ef4444',
  violet: '#8b5cf6',
  cyan: '#06b6d4',
}

const accent = computed(() => colorAccents[props.widget.color] ?? colorAccents.primary)

const isGrouped = computed(() => !!props.data?.groups && Object.keys(props.data.groups).length > 0)

const chartData = computed(() => {
  if (isGrouped.value) {
    const groups = props.data!.groups!
    return {
      labels: props.data?.labels ?? [],
      datasets: Object.entries(groups).map(([name, values], i) => ({
        label: name,
        data: values,
        backgroundColor: props.widget.widget_type === 'chart_area'
          ? PALETTE[i % PALETTE.length] + '44'
          : PALETTE[i % PALETTE.length] + 'cc',
        borderColor: PALETTE[i % PALETTE.length],
        borderWidth: 2,
        borderRadius: props.widget.widget_type === 'chart_bar' ? 4 : 0,
        fill: props.widget.widget_type === 'chart_area',
        tension: 0.4,
        pointRadius: 3,
      })),
    }
  }
  return {
    labels: props.data?.labels ?? [],
    datasets: [{
      label: props.widget.title,
      data: props.data?.values ?? [],
      backgroundColor: props.widget.widget_type === 'chart_area'
        ? accent.value + '33'
        : accent.value + 'cc',
      borderColor: accent.value,
      borderWidth: 2,
      borderRadius: props.widget.widget_type === 'chart_bar' ? 4 : 0,
      fill: props.widget.widget_type === 'chart_area',
      tension: 0.4,
      pointRadius: 3,
    }],
  }
})

// Report-sourced charts carry no `filters` and stay non-clickable.
const canOpen = computed(() => !!props.widget.doctype && !!props.widget.date_field && !!props.data?.filters)

/** The day column under the pointer (and, for a grouped chart, the nearest series). */
function hit(e: ChartEvent, chart: ChartInstance): ActiveElement | undefined {
  const mode = isGrouped.value ? 'nearest' : 'index'
  return chart.getElementsAtEventForMode(e as unknown as Event, mode, { intersect: false }, false)[0]
}

/** Day (and group) → the widget's list filtered to it. */
function onClick(e: ChartEvent, _els: ActiveElement[], chart: ChartInstance) {
  const { widget, data } = props
  const el = canOpen.value ? hit(e, chart) : undefined
  const range = el && periodRange('day', data!.labels[el.index])
  if (!el || !range) return
  const df = widget.date_field!
  const filters: Record<string, unknown> = { ...data!.filters, [`${df}__gte`]: range[0], [`${df}__lt`]: range[1] }
  if (isGrouped.value && widget.group_by) {
    filters[widget.group_by] = Object.keys(data!.groups!)[el.datasetIndex]
  }
  router.push(filteredListUrl(widget.doctype, filters, props.workspaceName))
}

function onHover(e: ChartEvent, _els: ActiveElement[], chart: ChartInstance) {
  const canvas = e.native?.target as HTMLElement | undefined
  if (canvas) canvas.style.cursor = canOpen.value && hit(e, chart) ? 'pointer' : 'default'
}

const chartOptions = computed(() => ({
  onClick,
  onHover,
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: isGrouped.value },
    tooltip: { mode: 'index' as const, intersect: false },
  },
  scales: {
    x: {
      grid: { display: false },
      ticks: { font: { size: 11 }, maxRotation: 0, maxTicksLimit: 8 },
    },
    y: {
      grid: { color: 'rgba(0,0,0,0.05)' },
      ticks: { font: { size: 11 } },
      beginAtZero: true,
    },
  },
}))
</script>

<template>
  <div class="flex flex-col gap-2 p-5 h-full">
    <p class="text-muted-foreground font-medium">{{ widget.title }}</p>

    <div v-if="loading" class="flex-1 bg-muted animate-pulse rounded" />

    <div v-else-if="!data?.labels?.length"
      class="flex-1 flex items-center justify-center text-muted-foreground">
      {{ t('No data') }}
    </div>

    <div v-else class="flex-1 min-h-0" style="min-height:140px">
      <Bar v-if="widget.widget_type === 'chart_bar'" :data="chartData" :options="chartOptions" />
      <Line v-else :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
