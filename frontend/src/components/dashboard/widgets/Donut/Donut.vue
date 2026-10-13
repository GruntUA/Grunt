<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { VisDonut, VisDonutSelectors, VisSingleContainer } from '@unovis/vue'
import type { DashboardWidget } from '@/types'
import { ChartContainer, ChartTooltip } from '@/components/ui/chart'
import { Skeleton } from '@/components/ui/skeleton'
import { seriesColor, seriesConfig, tooltipHtml } from '@/core/charts'
import { formatNumber } from '@/core/currency'
import { filteredListUrl, groupFilter } from '@/pages/reports/drilldown'

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

const total = computed(() => props.data?.values.reduce((a, b) => a + b, 0) ?? 0)

/** The legend: every group with its value and share (`<1%` rather than a misleading `0%`). */
const items = computed(() => (props.data?.labels ?? []).map((label, i) => {
  const value = props.data!.values[i] ?? 0
  const share = total.value ? (value / total.value) * 100 : 0
  return {
    label,
    value: formatNumber(value),
    share: share > 0 && share < 1 ? '<1%' : `${Math.round(share)}%`,
    color: seriesColor(i),
  }
}))

interface Segment { index: number; value: number }

const segments = computed<Segment[]>(() => (props.data?.values ?? []).map((value, index) => ({ index, value })))
const config = computed(() => seriesConfig(props.data?.labels ?? [], segments.value.map((s) => seriesColor(s.index))))

// unovis passes the arc datum (`{ data: Segment }`) to segment events and tooltips.
type Arc = { data: Segment }
const segmentEvents = {
  [VisDonutSelectors.segment]: { click: (d: Arc) => open(d.data.index) },
}
const triggers = {
  [VisDonutSelectors.segment]: (d: Arc) =>
    tooltipHtml({ payload: { [`s${d.data.index}`]: d.data.value }, config: config.value, hideLabel: true }),
}
</script>

<template>
  <div class="flex flex-col gap-3 p-5 h-full">
    <div class="flex items-start justify-between gap-2">
      <p class="text-muted-foreground font-medium">{{ widget.title }}</p>
      <span v-if="total" class="text-muted-foreground tabular-nums shrink-0">{{ formatNumber(total) }} {{ t('total') }}</span>
    </div>

    <Skeleton v-if="loading" class="flex-1" />

    <div v-else-if="!data?.labels?.length" class="flex-1 flex items-center justify-center text-muted-foreground">
      {{ t('No data') }}
    </div>

    <template v-else>
      <ChartContainer :config="config" class="aspect-auto h-36 shrink-0" :class="canOpen && 'cursor-pointer'">
        <VisSingleContainer :data="segments">
          <VisDonut
            :value="(d: Segment) => d.value"
            :color="(d: Segment) => seriesColor(d.index)"
            :arc-width="24"
            :pad-angle="0.02"
            :corner-radius="2"
            :events="segmentEvents"
          />
          <ChartTooltip :triggers="triggers" />
        </VisSingleContainer>
      </ChartContainer>

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
