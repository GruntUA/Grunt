<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { DashboardWidget } from '@/types'
import { filteredListUrl } from '@/pages/reports/drilldown'
import { useLucideIcons } from '@/core/composables/useLucideIcons'
import { formatNumber } from '@/core/currency'
import { TrendingUp, TrendingDown, Minus } from '@lucide/vue'

const { t } = useI18n()

const props = defineProps<{
  widget: DashboardWidget
  data: { value: number; trend?: number | null; previous?: number; filters?: Record<string, unknown> } | null
  loading?: boolean
  workspaceName?: string
}>()

const router = useRouter()
const { iconFor } = useLucideIcons()

/** Card -> the widget's list, filtered to the rows the value was computed over. */
const canOpen = computed(() => !!props.widget.ref_doctype && !!props.data?.filters)

function open() {
  if (!canOpen.value) return
  router.push(filteredListUrl(props.widget.ref_doctype, props.data!.filters!, props.workspaceName))
}

const iconComponent = computed(() => iconFor(props.widget.icon))

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

// Exact up to 10 000 (`2 498`), compact above (`577,5 тис.`).
function fmt(v: number): string {
  return Math.abs(v) < 10_000
    ? formatNumber(v, { maximumFractionDigits: 2 })
    : formatNumber(v, { notation: 'compact', maximumFractionDigits: 1 })
}

const formattedValue = computed(() => fmt(props.data?.value ?? 0))
const previous = computed(() => props.data?.previous ?? null)

const trend = computed(() => props.data?.trend ?? null)
const trendPositive = computed(() => (trend.value ?? 0) > 0)
const trendNeutral = computed(() => trend.value === null || trend.value === 0)
</script>

<template>
  <div
    :class="['flex flex-col gap-3 p-4 sm:p-5 h-full', canOpen && 'cursor-pointer hover:bg-muted/30 transition-colors']"
    @click="open">
    <!-- Header -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 text-muted-foreground font-medium">{{ widget.title }}</p>
      <div v-if="iconComponent" :class="['shrink-0 p-2 rounded-lg', iconBg]">
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
      <p class="text-2xl sm:text-3xl font-semibold tabular-nums tracking-tight text-foreground">{{ formattedValue }}</p>
      <!-- Description and the comparison with the previous period share one line,
           so a card with a trend is no taller than its neighbours. -->
      <div v-if="widget.description || trend !== null || previous !== null"
        class="-mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-muted-foreground">
        <span v-if="widget.description">{{ widget.description }}</span>
        <span v-if="widget.description && (trend !== null || previous !== null)" aria-hidden="true">·</span>
        <template v-if="trend !== null">
          <Minus v-if="trendNeutral" class="w-3.5 h-3.5" />
          <TrendingUp v-else-if="trendPositive" class="w-3.5 h-3.5 text-emerald-500" />
          <TrendingDown v-else class="w-3.5 h-3.5 text-red-500" />
          <span v-if="trendNeutral">{{ t('no change') }}</span>
          <span v-else :class="['font-medium', trendPositive ? 'text-emerald-600' : 'text-red-600']">
            {{ trendPositive ? '+' : '' }}{{ trend }}%
          </span>
        </template>
        <span v-if="previous !== null">{{ t('was {n}', { n: fmt(previous) }) }}</span>
      </div>
    </template>
  </div>
</template>
