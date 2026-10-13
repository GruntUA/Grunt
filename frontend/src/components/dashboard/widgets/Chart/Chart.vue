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
import { filteredListUrl } from '@/pages/reports/drilldown'
import { formatIntl } from '@/core/datetime'

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

// Day labels (`YYYY-MM-DD`) are re-bucketed: missing days become zeros, and a
// series longer than ~3 months is summed per week (Monday) - daily points over a
// year are a saw of spikes. Report-sourced labels (not dates) pass through as is.
const DAY_MS = 86_400_000
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/
const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10)
const dayMs = (label: string) => Date.parse(`${label}T00:00:00Z`)

const series = computed(() => {
  const labels = props.data?.labels ?? []
  const raw: number[][] = isGrouped.value
    ? Object.values(props.data!.groups!)
    : [props.data?.values ?? []]
  if (!labels.length || !labels.every((l) => DATE_RE.test(l))) {
    return { keys: labels, step: 0, values: raw }
  }
  const first = dayMs(labels[0])
  const last = dayMs(labels[labels.length - 1])
  const step = last - first > 92 * DAY_MS ? 7 : 1
  // Bucket start: the day itself, or its week's Monday.
  const start = (ms: number) => step === 1 ? ms : ms - ((new Date(ms).getUTCDay() + 6) % 7) * DAY_MS
  const keys: string[] = []
  for (let ms = start(first); ms <= last; ms += step * DAY_MS) keys.push(isoDay(ms))
  const index = new Map(keys.map((k, i) => [k, i]))
  const values = raw.map((vals) => {
    const out = new Array<number>(keys.length).fill(0)
    labels.forEach((l, i) => { out[index.get(isoDay(start(dayMs(l))))!] += Number(vals[i] ?? 0) })
    return out
  })
  return { keys, step, values }
})

/** `13 жовт.` for a day/week bucket; the raw label otherwise. */
function displayLabel(key: string): string {
  return series.value.step ? formatIntl(new Date(dayMs(key)), { day: 'numeric', month: 'short', timeZone: 'UTC' }) : key
}

const chartData = computed(() => {
  if (isGrouped.value) {
    const names = Object.keys(props.data!.groups!)
    return {
      labels: series.value.keys.map(displayLabel),
      datasets: names.map((name, i) => ({
        label: name,
        data: series.value.values[i],
        backgroundColor: props.widget.widget_type === 'chart_area'
          ? PALETTE[i % PALETTE.length] + '44'
          : PALETTE[i % PALETTE.length] + 'cc',
        borderColor: PALETTE[i % PALETTE.length],
        borderWidth: 2,
        borderRadius: props.widget.widget_type === 'chart_bar' ? 4 : 0,
        fill: props.widget.widget_type === 'chart_area',
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 4,
      })),
    }
  }
  return {
    labels: series.value.keys.map(displayLabel),
    datasets: [{
      label: props.widget.title,
      data: series.value.values[0],
      backgroundColor: props.widget.widget_type === 'chart_area'
        ? accent.value + '33'
        : accent.value + 'cc',
      borderColor: accent.value,
      borderWidth: 2,
      borderRadius: props.widget.widget_type === 'chart_bar' ? 4 : 0,
      fill: props.widget.widget_type === 'chart_area',
      tension: 0.3,
      pointRadius: 0,
      pointHoverRadius: 4,
    }],
  }
})

// Report-sourced charts carry no `filters` and stay non-clickable.
const canOpen = computed(() =>
  !!props.widget.ref_doctype && !!props.widget.date_field && !!props.data?.filters && !!series.value.step)

/** The day column under the pointer (and, for a grouped chart, the nearest series). */
function hit(e: ChartEvent, chart: ChartInstance): ActiveElement | undefined {
  const mode = isGrouped.value ? 'nearest' : 'index'
  return chart.getElementsAtEventForMode(e as unknown as Event, mode, { intersect: false }, false)[0]
}

/** Day/week (and group) -> the widget's list filtered to it. */
function onClick(e: ChartEvent, _els: ActiveElement[], chart: ChartInstance) {
  const { widget, data } = props
  const el = canOpen.value ? hit(e, chart) : undefined
  if (!el) return
  const { keys, step } = series.value
  const from = keys[el.index]
  const to = isoDay(dayMs(from) + step * DAY_MS)
  const df = widget.date_field!
  const filters: Record<string, unknown> = { ...data!.filters, [`${df}__gte`]: from, [`${df}__lt`]: to }
  if (isGrouped.value && widget.group_by) {
    filters[widget.group_by] = Object.keys(data!.groups!)[el.datasetIndex]
  }
  router.push(filteredListUrl(widget.ref_doctype, filters, props.workspaceName))
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
