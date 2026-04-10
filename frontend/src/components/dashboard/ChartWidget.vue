<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
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
import type { DashboardWidget } from '@/types'

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Filler, Tooltip, Legend)

const { t } = useI18n()

const props = defineProps<{
  widget: DashboardWidget
  data: { labels: string[]; values: number[] } | null
  loading?: boolean
}>()

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

const chartData = computed(() => ({
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
}))

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
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
    <p class="text-sm text-muted-foreground font-medium">{{ widget.title }}</p>

    <div v-if="loading" class="flex-1 bg-muted animate-pulse rounded" />

    <div v-else-if="!data?.labels?.length"
      class="flex-1 flex items-center justify-center text-muted-foreground text-sm">
      {{ t('No data') }}
    </div>

    <div v-else class="flex-1 min-h-0" style="min-height:140px">
      <Bar v-if="widget.widget_type === 'chart_bar'" :data="chartData" :options="chartOptions" />
      <Line v-else :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
