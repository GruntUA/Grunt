<script setup lang="ts">
import { computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import type { DashboardWidget } from '@/types'

ChartJS.register(ArcElement, Tooltip, Legend)

const props = defineProps<{
  widget: DashboardWidget
  data: { labels: string[]; values: number[] } | null
  loading?: boolean
}>()

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
    borderColor: 'hsl(var(--card))',
    hoverOffset: 6,
  }],
}))

const chartOptions = {
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
      <p class="text-sm text-muted-foreground font-medium">{{ widget.title }}</p>
      <span v-if="total" class="text-xs text-muted-foreground tabular-nums">{{ total }} всього</span>
    </div>

    <div v-if="loading" class="flex-1 bg-muted animate-pulse rounded" />

    <div v-else-if="!data?.labels?.length" class="flex-1 flex items-center justify-center text-muted-foreground text-sm">
      Немає даних
    </div>

    <div v-else class="flex-1 min-h-0" style="min-height:160px">
      <Doughnut :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
