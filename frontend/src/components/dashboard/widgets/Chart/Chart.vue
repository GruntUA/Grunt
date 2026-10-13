<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { VisArea, VisAxis, VisGroupedBar, VisGroupedBarSelectors, VisLine, VisXYContainer } from '@unovis/vue'
import type { DashboardWidget } from '@/types'
import { ChartContainer, ChartCrosshair, ChartTooltip } from '@/components/ui/chart'
import { Skeleton } from '@/components/ui/skeleton'
import { accentColor, seriesColor, seriesConfig, tooltipHtml } from '@/core/charts'
import { filteredListUrl } from '@/pages/reports/drilldown'
import { formatIntl } from '@/core/datetime'

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

interface Row { idx: number; [series: string]: number }

const names = computed(() => isGrouped.value ? Object.keys(props.data!.groups!) : [props.widget.title])
const colors = computed(() => isGrouped.value ? names.value.map((_, i) => seriesColor(i)) : [accentColor(props.widget.color)])
const config = computed(() => seriesConfig(names.value, colors.value))

/** One row per bucket: `{ idx, s0, s1, … }`. */
const rows = computed<Row[]>(() => series.value.keys.map((_, idx) => {
  const row: Row = { idx }
  series.value.values.forEach((vals, s) => { row[`s${s}`] = vals[idx] ?? 0 })
  return row
}))
const x = (d: Row) => d.idx
const ys = computed(() => names.value.map((_, s) => (d: Row) => d[`s${s}`]))
const labelAt = (i: number) => displayLabel(series.value.keys[Math.round(i)] ?? '')

// Report-sourced charts carry no `filters` and stay non-clickable.
const canOpen = computed(() =>
  !!props.widget.ref_doctype && !!props.widget.date_field && !!props.data?.filters && !!series.value.step)

/** Day/week bucket (and, for grouped bars, the series) -> the widget's list filtered to it. */
function open(index: number, seriesIndex?: number) {
  const { widget, data } = props
  if (!canOpen.value) return
  const { keys, step } = series.value
  const from = keys[index]
  const to = isoDay(dayMs(from) + step * DAY_MS)
  const df = widget.date_field!
  const filters: Record<string, unknown> = { ...data!.filters, [`${df}__gte`]: from, [`${df}__lt`]: to }
  if (isGrouped.value && widget.group_by && seriesIndex !== undefined) {
    filters[widget.group_by] = names.value[seriesIndex]
  }
  router.push(filteredListUrl(widget.ref_doctype, filters, props.workspaceName))
}

// Lines and areas: the crosshair tracks the bucket under the pointer, a click opens it.
let hovered: number | null = null
function crosshair(d: Row) {
  hovered = d.idx
  return tooltipHtml({ payload: d, config: config.value, x: d.idx, labelFormatter: (i) => labelAt(Number(i)) })
}
function onAreaClick() {
  if (hovered !== null) open(hovered)
}

const barEvents = {
  [VisGroupedBarSelectors.bar]: { click: (d: Row, i: number) => open(d.idx, i) },
}
</script>

<template>
  <div class="flex flex-col gap-2 p-5 h-full">
    <p class="text-muted-foreground font-medium">{{ widget.title }}</p>

    <Skeleton v-if="loading" class="flex-1" />

    <div v-else-if="!data?.labels?.length"
      class="flex-1 flex items-center justify-center text-muted-foreground">
      {{ t('No data') }}
    </div>

    <ChartContainer
      v-else
      :config="config"
      class="aspect-auto min-h-[140px] flex-1"
      :class="canOpen && 'cursor-pointer'"
      @click="widget.widget_type !== 'chart_bar' && onAreaClick()"
    >
      <VisXYContainer :data="rows" :y-domain="[0, undefined]" :margin="{ left: 4, right: 4 }">
        <VisGroupedBar
          v-if="widget.widget_type === 'chart_bar'"
          :x="x" :y="ys" :color="colors" :rounded-corners="4" :bar-padding="0.1" :events="barEvents"
        />
        <template v-else>
          <template v-for="(y, s) in ys" :key="s">
            <VisArea v-if="widget.widget_type === 'chart_area'" :x="x" :y="y" :color="colors[s]" :opacity="0.25" />
            <VisLine :x="x" :y="y" :color="colors[s]" :line-width="2" curve-type="monotoneX" />
          </template>
        </template>
        <VisAxis
          type="x" :x="x" :tick-format="labelAt" :num-ticks="Math.min(8, rows.length)"
          :tick-line="false" :domain-line="false" :grid-line="false"
        />
        <VisAxis type="y" :num-ticks="4" :tick-line="false" :domain-line="false" />
        <ChartTooltip />
        <ChartCrosshair :template="crosshair" :color="colors" />
      </VisXYContainer>
    </ChartContainer>
  </div>
</template>
