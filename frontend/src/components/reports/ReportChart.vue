<script setup lang="ts">
import { computed, ref } from 'vue'
import { Bar, Line, Pie, Doughnut } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  ArcElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js'
import type { ReportChartConfig, ReportColumn } from '@/types'

ChartJS.register(
  CategoryScale, LinearScale, BarElement, PointElement, LineElement, ArcElement,
  Filler, Tooltip, Legend,
)

const props = defineProps<{
  config: ReportChartConfig
  columns: ReportColumn[]
  data: Record<string, unknown>[]
}>()

const PALETTE = [
  '#2D6A4F', '#3b82f6', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#10b981', '#f97316',
]

const kind = computed(() => props.config.type)
const isPieLike = computed(() => kind.value === 'pie' || kind.value === 'donut')

function labelFor(fieldname: string): string {
  return props.columns.find(c => c.fieldname === fieldname)?.label ?? fieldname
}

function toNumber(v: unknown): number {
  const n = typeof v === 'number' ? v : parseFloat(String(v ?? ''))
  return Number.isFinite(n) ? n : 0
}

const labels = computed(() =>
  props.data.map(row => String(row[props.config.label_field] ?? '—')),
)

const chartData = computed(() => {
  const valueFields = props.config.value_fields.length
    ? props.config.value_fields
    : props.columns.filter(c => c.fieldname !== props.config.label_field).map(c => c.fieldname).slice(0, 1)

  if (isPieLike.value) {
    const field = valueFields[0]
    return {
      labels: labels.value,
      datasets: [{
        data: props.data.map(row => toNumber(row[field])),
        backgroundColor: props.data.map((_, i) => PALETTE[i % PALETTE.length]),
        borderWidth: 0,
      }],
    }
  }

  return {
    labels: labels.value,
    datasets: valueFields.map((field, i) => {
      const accent = valueFields.length === 1 && props.config.color
        ? props.config.color
        : PALETTE[i % PALETTE.length]
      return {
        label: labelFor(field),
        data: props.data.map(row => toNumber(row[field])),
        backgroundColor: kind.value === 'area' ? accent + '33' : accent + 'cc',
        borderColor: accent,
        borderWidth: 2,
        borderRadius: kind.value === 'bar' ? 4 : 0,
        fill: kind.value === 'area',
        tension: 0.4,
        pointRadius: 3,
      }
    }),
  }
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  plugins: {
    legend: {
      display: isPieLike.value || props.config.value_fields.length > 1,
      position: (isPieLike.value ? 'right' : 'top') as 'right' | 'top',
    },
    tooltip: { mode: (isPieLike.value ? 'nearest' : 'index') as 'nearest' | 'index', intersect: false },
  },
  scales: isPieLike.value ? {} : {
    x: {
      stacked: !!props.config.stacked,
      grid: { display: false },
      ticks: { font: { size: 11 }, maxRotation: 0, maxTicksLimit: 12 },
    },
    y: {
      stacked: !!props.config.stacked,
      grid: { color: 'rgba(128,128,128,0.15)' },
      ticks: { font: { size: 11 } },
      beginAtZero: true,
    },
  },
}))

const chartRef = ref<any>(null)

/** Returns a PNG data URL of the current chart, or null if not ready. */
function toPng(): string | null {
  return chartRef.value?.chart?.toBase64Image?.('image/png', 1) ?? null
}

defineExpose({ toPng })
</script>

<template>
  <div class="h-[360px] w-full">
    <Bar v-if="kind === 'bar'" ref="chartRef" :data="chartData" :options="chartOptions" />
    <Line v-else-if="kind === 'line' || kind === 'area'" ref="chartRef" :data="chartData" :options="chartOptions" />
    <Pie v-else-if="kind === 'pie'" ref="chartRef" :data="chartData" :options="chartOptions" />
    <Doughnut v-else-if="kind === 'donut'" ref="chartRef" :data="chartData" :options="chartOptions" />
  </div>
</template>
