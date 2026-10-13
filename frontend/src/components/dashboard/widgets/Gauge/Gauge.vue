<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { VisDonut, VisSingleContainer } from '@unovis/vue'
import type { DashboardWidget } from '@/types'
import { ChartContainer } from '@/components/ui/chart'
import { Skeleton } from '@/components/ui/skeleton'
import { accentColor } from '@/core/charts'
import { filteredListUrl } from '@/pages/reports/drilldown'

const props = defineProps<{
  widget: DashboardWidget
  data: { value: number; trend?: number | null; filters?: Record<string, unknown> } | null
  loading?: boolean
  workspaceName?: string
}>()

const router = useRouter()

/** Gauge -> the widget's list, filtered to the rows the value was computed over. */
const canOpen = computed(() => !!props.widget.ref_doctype && !!props.data?.filters)

function open() {
  if (!canOpen.value) return
  router.push(filteredListUrl(props.widget.ref_doctype, props.data!.filters!, props.workspaceName))
}

const accent = computed(() => accentColor(props.widget.color))

const minVal = computed(() => props.widget.min_value ?? 0)
const maxVal = computed(() => props.widget.max_value ?? 100)
const value  = computed(() => props.data?.value ?? 0)

const pct = computed(() => {
  const range = maxVal.value - minVal.value
  if (range <= 0) return 0
  return Math.max(0, Math.min(1, (value.value - minVal.value) / range))
})

// The filled share, then the rest of the scale in the muted track colour.
const arcs = computed(() => [pct.value, 1 - pct.value])
const arcColor = (_: number, i: number) => (i === 0 ? accent.value : 'var(--muted)')

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
  <div
    :class="['flex flex-col gap-1 p-5 h-full', canOpen && 'cursor-pointer hover:bg-muted/30 transition-colors']"
    @click="open">
    <p class="text-muted-foreground font-medium">{{ widget.title }}</p>

    <!-- Skeleton -->
    <Skeleton v-if="loading" class="flex-1" />

    <div v-else class="flex-1 relative flex flex-col items-center justify-center" style="min-height:140px">
      <!-- Half ring: a full-size donut drawn over the top half (angleRange), the
           box shows only its upper half -->
      <div class="w-full overflow-hidden" style="height:55%">
        <ChartContainer :config="{}" class="aspect-auto h-[200%]">
          <VisSingleContainer :data="arcs">
            <VisDonut
              :value="(d: number) => d"
              :color="arcColor"
              :angle-range="[-Math.PI / 2, Math.PI / 2]"
              :arc-width="18"
              :corner-radius="4"
              :show-empty-segments="true"
            />
          </VisSingleContainer>
        </ChartContainer>
      </div>

      <!-- Value overlay centered below the arc -->
      <div class="flex flex-col items-center gap-0.5 mt-1">
        <p class="text-2xl font-semibold tabular-nums tracking-tight" :style="{ color: accent }">
          {{ formattedValue }}
        </p>
        <p class="text-muted-foreground tabular-nums">
          {{ minVal }} – {{ maxVal }}
        </p>
        <!-- Trend indicator -->
        <p v-if="trend !== null" class="font-medium"
          :class="trend === 0 ? 'text-muted-foreground' : trendPos ? 'text-emerald-600' : 'text-red-500'">
          {{ trendPos ? '+' : '' }}{{ trend }}%
        </p>
      </div>
    </div>
  </div>
</template>
