<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardWidget } from '@/types'
import * as LucideIcons from '@lucide/vue'
import { TrendingUp, TrendingDown, Minus } from '@lucide/vue'

const props = defineProps<{
  widget: DashboardWidget
  data: { value: number; trend?: number | null } | null
  loading?: boolean
}>()

const iconComponent = computed(() => {
  if (!props.widget.icon) return null
  return (LucideIcons as Record<string, unknown>)[props.widget.icon] ?? null
})

const colorMap: Record<string, string> = {
  primary:     'bg-primary/10 text-primary',
  blue:        'bg-blue-500/10 text-blue-600',
  green:       'bg-emerald-500/10 text-emerald-600',
  amber:       'bg-amber-500/10 text-amber-600',
  red:         'bg-red-500/10 text-red-600',
  violet:      'bg-violet-500/10 text-violet-600',
  cyan:        'bg-cyan-500/10 text-cyan-600',
}

const iconBg = computed(() => colorMap[props.widget.color] ?? colorMap.primary)

const formattedValue = computed(() => {
  const v = props.data?.value ?? 0
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M'
  if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K'
  return Number.isInteger(v) ? v.toString() : v.toFixed(2)
})

const trend = computed(() => props.data?.trend ?? null)
const trendPositive = computed(() => (trend.value ?? 0) > 0)
const trendNeutral = computed(() => trend.value === null || trend.value === 0)
</script>

<template>
  <div class="flex flex-col gap-3 p-5 h-full">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <p class="text-muted-foreground font-medium">{{ widget.title }}</p>
      <div v-if="iconComponent" :class="['p-2 rounded-lg', iconBg]">
        <component :is="iconComponent" class="w-4 h-4" />
      </div>
    </div>

    <!-- Skeleton -->
    <template v-if="loading">
      <div class="h-8 w-24 bg-muted animate-pulse rounded" />
      <div class="h-4 w-16 bg-muted animate-pulse rounded" />
    </template>

    <!-- Value -->
    <template v-else>
      <p class="text-3xl font-semibold tabular-nums tracking-tight text-foreground">{{ formattedValue }}</p>

      <!-- Trend badge -->
      <div v-if="trend !== null" class="flex items-center gap-1 text-xs">
        <template v-if="trendNeutral">
          <Minus class="w-3.5 h-3.5 text-muted-foreground" />
          <span class="text-muted-foreground">без змін</span>
        </template>
        <template v-else-if="trendPositive">
          <TrendingUp class="w-3.5 h-3.5 text-emerald-500" />
          <span class="text-emerald-600 font-medium">+{{ trend }}%</span>
          <span class="text-muted-foreground">за {{ widget.period }}</span>
        </template>
        <template v-else>
          <TrendingDown class="w-3.5 h-3.5 text-red-500" />
          <span class="text-red-600 font-medium">{{ trend }}%</span>
          <span class="text-muted-foreground">за {{ widget.period }}</span>
        </template>
      </div>
    </template>
  </div>
</template>
