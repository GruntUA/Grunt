<script setup lang="ts">
import { computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
} from 'chart.js'
import type { DashboardWidget } from '@/types'

ChartJS.register(ArcElement, Tooltip)

const props = defineProps<{
  widget: DashboardWidget
  data: { value: number; trend?: number | null } | null
  loading?: boolean
}>()

const colorAccents: Record<string, string> = {
  primary: '#2D6A4F',
  blue:    '#3b82f6',
  green:   '#10b981',
  amber:   '#f59e0b',
  red:     '#ef4444',
  violet:  '#8b5cf6',
  cyan:    '#06b6d4',
}

const accent = computed(() => colorAccents[props.widget.color] ?? colorAccents.primary)

const minVal = computed(() => props.widget.min_value ?? 0)
const maxVal = computed(() => props.widget.max_value ?? 100)
const value  = computed(() => props.data?.value ?? 0)

const pct = computed(() => {
  const range = maxVal.value - minVal.value
  if (range <= 0) return 0
  return Math.max(0, Math.min(1, (value.value - minVal.value) / range))
})

const chartData = computed(() => ({
  datasets: [{
    data: [pct.value, 1 - pct.value],
    backgroundColor: [accent.value, 'rgba(0,0,0,0.07)'],
    borderWidth: 0,
    hoverOffset: 0,
  }],
}))

const chartOptions = computed(() => ({
  circumference: 180,
  rotation: 270,
  cutout: '76%',
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 600 },
  plugins: {
    legend:  { display: false },
    tooltip: { enabled: false },
  },
}))

const formattedValue = computed(() => {
  const v = value.value
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M'
  if (v >= 1_000)     return (v / 1_000).toFixed(1) + 'K'
  return Number.isInteger(v) ? v.toString() : v.toFixed(2)
})

const trend    = computed(() => props.data?.trend ?? null)
const trendPos = computed(() => (trend.value ?? 0) > 0)
</script>

<template>
  <div class="flex flex-col gap-1 p-5 h-full">
    <p class="text-muted-foreground font-medium">{{ widget.title }}</p>

    <!-- Skeleton -->
    <div v-if="loading" class="flex-1 bg-muted animate-pulse rounded" />

    <div v-else class="flex-1 relative flex flex-col items-center justify-center" style="min-height:140px">
      <!-- Half-doughnut canvas — top 55% of the area -->
      <div class="w-full" style="height:55%">
        <Doughnut :data="chartData" :options="(chartOptions as any)" />
      </div>

      <!-- Value overlay centered below the arc -->
      <div class="flex flex-col items-center gap-0.5 mt-1">
        <p class="text-2xl font-semibold tabular-nums tracking-tight" :style="{ color: accent }">
          {{ formattedValue }}
        </p>
        <p class="text-xs text-muted-foreground tabular-nums">
          {{ minVal }} – {{ maxVal }}
        </p>
        <!-- Trend indicator -->
        <p v-if="trend !== null" class="text-xs font-medium"
          :class="trend === 0 ? 'text-muted-foreground' : trendPos ? 'text-emerald-600' : 'text-red-500'">
          {{ trendPos ? '+' : '' }}{{ trend }}%
        </p>
      </div>
    </div>
  </div>
</template>
