<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { Doughnut } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip } from 'chart.js'
import type { ActiveElement, ChartEvent } from 'chart.js'
import type { DashboardWidget } from '@/types'
import { formatNumber } from '@/core/currency'
import { filteredListUrl, groupFilter } from '@/pages/reports/drilldown'

ChartJS.register(ArcElement, Tooltip)

const { t } = useI18n()

const props = defineProps<{
  widget: DashboardWidget
  data: { labels: string[]; values: number[]; keys?: unknown[]; filters?: Record<string, unknown> } | null
  loading?: boolean
  workspaceName?: string
}>()

const router = useRouter()

// Report-sourced donuts carry no `keys`/`filters` and stay non-clickable.
const canOpen = computed(() => !!props.widget.ref_doctype && !!props.widget.group_by && !!props.data?.keys)

/** Group -> the widget's list filtered to it. */
function open(index: number) {
  const { widget, data } = props
  if (!canOpen.value) return
  router.push(filteredListUrl(
    widget.ref_doctype,
    { ...data!.filters, ...groupFilter(widget.group_by!, data!.keys![index]) },
    props.workspaceName,
  ))
}

function onClick(_e: ChartEvent, els: ActiveElement[]) {
  if (els.length) open(els[0].index)
}

function onHover(e: ChartEvent, els: ActiveElement[]) {
  const canvas = e.native?.target as HTMLElement | undefined
  if (canvas) canvas.style.cursor = canOpen.value && els.length ? 'pointer' : 'default'
}

const PALETTE = [
  '#2D6A4F', '#3b82f6', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#10b981', '#f97316',
]

const total = computed(() => props.data?.values.reduce((a, b) => a + b, 0) ?? 0)

/** The legend: every group with its value and share (`<1%` rather than a misleading `0%`). */
const items = computed(() => (props.data?.labels ?? []).map((label, i) => {
  const value = props.data!.values[i] ?? 0
  const share = total.value ? (value / total.value) * 100 : 0
  return {
    label,
    value: formatNumber(value),
    share: share > 0 && share < 1 ? '<1%' : `${Math.round(share)}%`,
    color: PALETTE[i % PALETTE.length],
  }
}))

const chartData = computed(() => ({
  labels: props.data?.labels ?? [],
  datasets: [{
    data: props.data?.values ?? [],
    backgroundColor: PALETTE,
    borderWidth: 2,
    borderColor: getComputedStyle(document.documentElement).getPropertyValue('--card').trim() || '#ffffff',
    hoverOffset: 4,
  }],
}))

const chartOptions = {
  onClick,
  onHover,
  responsive: true,
  maintainAspectRatio: false,
  cutout: '70%',
  plugins: {
    legend: { display: false },
    tooltip: { mode: 'index' as const },
  },
}
</script>

<template>
  <div class="flex flex-col gap-3 p-5 h-full">
    <div class="flex items-start justify-between gap-2">
      <p class="text-muted-foreground font-medium">{{ widget.title }}</p>
      <span v-if="total" class="text-muted-foreground tabular-nums shrink-0">{{ formatNumber(total) }} {{ t('total') }}</span>
    </div>

    <div v-if="loading" class="flex-1 bg-muted animate-pulse rounded" />

    <div v-else-if="!data?.labels?.length" class="flex-1 flex items-center justify-center text-muted-foreground">
      {{ t('No data') }}
    </div>

    <template v-else>
      <div class="h-36 shrink-0">
        <Doughnut :data="chartData" :options="chartOptions" />
      </div>

      <ul class="flex flex-col">
        <li
          v-for="(item, i) in items" :key="item.label"
          :class="['flex items-center gap-2 py-1 rounded', canOpen && 'cursor-pointer hover:bg-muted/40']"
          @click="open(i)"
        >
          <span class="size-2.5 rounded-[2px] shrink-0" :style="{ background: item.color }" />
          <span class="flex-1 min-w-0 truncate">{{ item.label }}</span>
          <span class="tabular-nums font-medium">{{ item.value }}</span>
          <span class="w-10 text-right tabular-nums text-muted-foreground">{{ item.share }}</span>
        </li>
      </ul>
    </template>
  </div>
</template>
