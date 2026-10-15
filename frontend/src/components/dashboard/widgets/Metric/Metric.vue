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

const iconColorMap: Record<string, string> = {
  primary: 'text-muted-foreground',
  blue:    'text-blue-500 dark:text-blue-400',
  green:   'text-emerald-500 dark:text-emerald-400',
  amber:   'text-amber-500 dark:text-amber-400',
  red:     'text-rose-500 dark:text-rose-400',
  violet:  'text-violet-500 dark:text-violet-400',
  cyan:    'text-cyan-500 dark:text-cyan-400',
}

const iconColor = computed(() => iconColorMap[props.widget.color] ?? 'text-muted-foreground')

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
    :class="[
      'flex flex-col justify-between gap-2 p-4 h-full select-none',
      canOpen && 'cursor-pointer hover:bg-muted/40 transition-colors',
    ]"
    @click="open"
  >
    <!-- Header: Title & Icon -->
    <div class="flex items-center justify-between gap-2">
      <span
        class="text-sm font-medium text-muted-foreground tracking-tight truncate"
        :title="widget.title"
      >
        {{ widget.title }}
      </span>
      <component
        :is="iconComponent"
        v-if="iconComponent"
        :class="['size-4 shrink-0', iconColor]"
      />
    </div>

    <!-- Body: Value & Subtitle -->
    <div class="space-y-1">
      <!-- Skeleton -->
      <template v-if="loading">
        <div class="h-7 w-20 bg-muted animate-pulse rounded" />
        <div class="h-3.5 w-32 bg-muted animate-pulse rounded" />
      </template>

      <!-- Value & Subtitle -->
      <template v-else>
        <div class="text-2xl font-bold tracking-tight tabular-nums text-foreground">
          {{ formattedValue }}
        </div>
        <!-- Description and comparison -->
        <div
          v-if="widget.description || trend !== null || previous !== null"
          class="text-xs text-muted-foreground flex flex-wrap items-center gap-x-1.5 gap-y-0.5"
        >
          <span v-if="widget.description">{{ widget.description }}</span>
          <span v-if="widget.description && (trend !== null || previous !== null)" aria-hidden="true">·</span>
          <template v-if="trend !== null">
            <Minus v-if="trendNeutral" class="size-3 text-muted-foreground shrink-0" />
            <TrendingUp v-else-if="trendPositive" class="size-3 text-emerald-500 shrink-0" />
            <TrendingDown v-else class="size-3 text-rose-500 shrink-0" />
            <span v-if="trendNeutral">{{ t('no change') }}</span>
            <span
              v-else
              :class="['font-medium', trendPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400']"
            >
              {{ trendPositive ? '+' : '' }}{{ trend }}%
            </span>
          </template>
          <span v-if="previous !== null">{{ t('was {n}', { n: fmt(previous) }) }}</span>
        </div>
      </template>
    </div>
  </div>
</template>
