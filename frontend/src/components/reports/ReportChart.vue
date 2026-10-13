<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  VisArea, VisAxis, VisDonut, VisDonutSelectors, VisGroupedBar, VisLine,
  VisSingleContainer, VisStackedBar, VisXYContainer,
} from '@unovis/vue'
import type { ReportChartConfig, ReportColumn } from '@/types'
import { ChartContainer, ChartCrosshair, ChartLegendContent, ChartTooltip } from '@/components/ui/chart'
import { chartToPng, seriesColor, seriesConfig, tooltipHtml } from '@/core/charts'

const props = defineProps<{
  config: ReportChartConfig
  columns: ReportColumn[]
  data: Record<string, unknown>[]
}>()

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

const valueFields = computed(() => props.config.value_fields.length
  ? props.config.value_fields
  : props.columns.filter(c => c.fieldname !== props.config.label_field).map(c => c.fieldname).slice(0, 1))

// XY charts: one series per value field; the report colour applies to a lone series.
const colors = computed(() => valueFields.value.map((_, i) =>
  valueFields.value.length === 1 && props.config.color ? props.config.color : seriesColor(i)))

interface Row { idx: number; [series: string]: number }

const rows = computed<Row[]>(() => props.data.map((row, idx) => {
  const out: Row = { idx }
  valueFields.value.forEach((f, s) => { out[`s${s}`] = toNumber(row[f]) })
  return out
}))
const x = (d: Row) => d.idx
const ys = computed(() => valueFields.value.map((_, s) => (d: Row) => d[`s${s}`]))
const labelAt = (i: number) => labels.value[Math.round(i)] ?? ''

// Pie/donut: one segment per row, coloured in turn; the first value field is the size.
const segmentColors = computed(() => props.data.map((_, i) => seriesColor(i)))
const config = computed(() => isPieLike.value
  ? seriesConfig(labels.value, segmentColors.value)
  : seriesConfig(valueFields.value.map(labelFor), colors.value))

// A lone XY series needs no legend - the chart title names it.
const showLegend = computed(() => isPieLike.value || valueFields.value.length > 1)

function crosshair(d: Row) {
  return tooltipHtml({ payload: d, config: config.value, x: d.idx, labelFormatter: (i) => labelAt(Number(i)) })
}
type Arc = { data: Row }
const triggers = {
  [VisDonutSelectors.segment]: (d: Arc) =>
    tooltipHtml({ payload: { [`s${d.data.idx}`]: d.data.s0 }, config: config.value, hideLabel: true }),
}

const root = ref<HTMLElement | null>(null)

/** PNG data URL of the current chart, or null if not ready. */
function toPng(): Promise<string | null> {
  return root.value ? chartToPng(root.value) : Promise.resolve(null)
}

defineExpose({ toPng })
</script>

<template>
  <div ref="root" class="h-[360px] w-full">
    <ChartContainer :config="config" class="aspect-auto">
      <VisSingleContainer v-if="isPieLike" :data="rows">
        <VisDonut
          :value="(d: Row) => d.s0"
          :color="(d: Row) => segmentColors[d.idx]"
          :arc-width="kind === 'donut' ? 48 : 0"
          :pad-angle="0.01"
        />
        <ChartTooltip :triggers="triggers" />
      </VisSingleContainer>

      <VisXYContainer v-else :data="rows" :y-domain="[0, undefined]" :margin="{ left: 4, right: 4 }">
        <template v-if="kind === 'bar'">
          <VisStackedBar v-if="props.config.stacked" :x="x" :y="ys" :color="colors" :rounded-corners="4" />
          <VisGroupedBar v-else :x="x" :y="ys" :color="colors" :rounded-corners="4" :bar-padding="0.1" />
        </template>
        <template v-else>
          <template v-for="(y, s) in ys" :key="s">
            <VisArea v-if="kind === 'area'" :x="x" :y="y" :color="colors[s]" :opacity="0.25" />
            <VisLine :x="x" :y="y" :color="colors[s]" :line-width="2" curve-type="monotoneX" />
          </template>
        </template>
        <VisAxis
          type="x" :x="x" :tick-format="labelAt" :num-ticks="Math.min(12, rows.length)"
          :tick-line="false" :domain-line="false" :grid-line="false"
        />
        <VisAxis type="y" :num-ticks="5" :tick-line="false" :domain-line="false" />
        <ChartTooltip />
        <ChartCrosshair :template="crosshair" :color="colors" />
      </VisXYContainer>
      <ChartLegendContent v-if="showLegend" class="flex-wrap" />
    </ChartContainer>
  </div>
</template>
