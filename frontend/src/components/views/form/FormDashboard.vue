<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  X,
  Plus,
  ArrowUpRight,
  Info,
  AlertCircle,
  FileText,
} from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useElementSize } from '@vueuse/core'
import type { FormDashboardState } from '@/core/scripting/formDashboard'
import { appUrl } from '@/core/workspaceUrl'
import { formatIntl } from '@/core/datetime'
import { formatCurrency, formatNumber } from '@/core/currency'

const { t } = useI18n()
const router = useRouter()

const props = defineProps<{
  dashboard: FormDashboardState
  doctype?: string | { name: string; label?: string }
  document?: Record<string, any>
  workspace?: string
}>()

const emit = defineEmits<{
  'create-new': [doctype: string, preset: Record<string, unknown>, fieldname: string]
}>()

const doctypeName = computed(() => {
  if (!props.doctype) return ''
  return typeof props.doctype === 'string' ? props.doctype : props.doctype.name
})

const docId = computed(() => {
  return props.document?.name ?? props.document?.id ?? ''
})

// Color helper for badges, indicators, headlines, comments
function resolveColorClasses(color?: string): {
  bg: string
  border: string
  text: string
  dot: string
  badgeVariant?: 'default' | 'secondary' | 'destructive' | 'outline'
} {
  const c = (color || 'blue').toLowerCase()
  if (c === 'green' || c === 'success') {
    return {
      bg: 'bg-emerald-500/10 dark:bg-emerald-500/15',
      border: 'border-emerald-500/30 dark:border-emerald-500/40',
      text: 'text-emerald-800 dark:text-emerald-300',
      dot: 'bg-emerald-500',
      badgeVariant: 'outline',
    }
  }
  if (c === 'red' || c === 'danger' || c === 'error') {
    return {
      bg: 'bg-rose-500/10 dark:bg-rose-500/15',
      border: 'border-rose-500/30 dark:border-rose-500/40',
      text: 'text-rose-800 dark:text-rose-300',
      dot: 'bg-rose-500',
      badgeVariant: 'destructive',
    }
  }
  if (c === 'orange' || c === 'warning' || c === 'amber') {
    return {
      bg: 'bg-amber-500/10 dark:bg-amber-500/15',
      border: 'border-amber-500/30 dark:border-amber-500/40',
      text: 'text-amber-800 dark:text-amber-300',
      dot: 'bg-amber-500',
      badgeVariant: 'outline',
    }
  }
  if (c === 'purple' || c === 'violet') {
    return {
      bg: 'bg-purple-500/10 dark:bg-purple-500/15',
      border: 'border-purple-500/30 dark:border-purple-500/40',
      text: 'text-purple-800 dark:text-purple-300',
      dot: 'bg-purple-500',
      badgeVariant: 'outline',
    }
  }
  if (c === 'cyan' || c === 'teal') {
    return {
      bg: 'bg-cyan-500/10 dark:bg-cyan-500/15',
      border: 'border-cyan-500/30 dark:border-cyan-500/40',
      text: 'text-cyan-800 dark:text-cyan-300',
      dot: 'bg-cyan-500',
      badgeVariant: 'outline',
    }
  }
  if (c === 'gray' || c === 'grey' || c === 'muted') {
    return {
      bg: 'bg-muted/60',
      border: 'border-border',
      text: 'text-muted-foreground',
      dot: 'bg-muted-foreground',
      badgeVariant: 'secondary',
    }
  }
  // Default blue / primary
  return {
    bg: 'bg-sky-500/10 dark:bg-sky-500/15',
    border: 'border-sky-500/30 dark:border-sky-500/40',
    text: 'text-sky-800 dark:text-sky-300',
    dot: 'bg-sky-500',
    badgeVariant: 'outline',
  }
}

function resolveProgressSegmentColor(color?: string): string {
  if (!color) return 'bg-primary'
  const c = color.toLowerCase()
  if (c === 'green' || c === 'success') return 'bg-emerald-500'
  if (c === 'red' || c === 'danger') return 'bg-rose-500'
  if (c === 'orange' || c === 'warning' || c === 'amber') return 'bg-amber-500'
  if (c === 'purple' || c === 'violet') return 'bg-purple-500'
  if (c === 'cyan' || c === 'teal') return 'bg-cyan-500'
  if (c === 'blue' || c === 'info') return 'bg-sky-500'
  return color.startsWith('#') || color.startsWith('rgb') ? '' : 'bg-primary'
}

function dismissHeadline() {
  if (props.dashboard.headline && !props.dashboard.headline.permanent) {
    props.dashboard.headline = null
  }
}

function dismissComment(idx: number) {
  const c = props.dashboard.comments[idx]
  if (c && !c.permanent) {
    props.dashboard.comments.splice(idx, 1)
  }
}

// ── Heatmap logic ──
const heatmapDays = computed(() => props.dashboard.heatmap?.days ?? 365)
const heatmapCounts = computed(() => {
  const map = new Map<string, number>()
  for (const e of props.dashboard.heatmap?.entries ?? []) {
    map.set(e.date.slice(0, 10), e.count)
  }
  return map
})

const heatmapWeeks = computed(() => {
  const map = heatmapCounts.value
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const cur = new Date(today)
  cur.setDate(cur.getDate() - (heatmapDays.value - 1))
  cur.setDate(cur.getDate() - ((cur.getDay() + 6) % 7)) // Start on Monday

  const weeks: { date: Date; key: string; count: number; future: boolean }[][] = []
  while (cur <= today) {
    const week: { date: Date; key: string; count: number; future: boolean }[] = []
    for (let d = 0; d < 7; d++) {
      const p = (n: number) => String(n).padStart(2, '0')
      const key = `${cur.getFullYear()}-${p(cur.getMonth() + 1)}-${p(cur.getDate())}`
      week.push({
        date: new Date(cur),
        key,
        count: map.get(key) ?? 0,
        future: cur > today,
      })
      cur.setDate(cur.getDate() + 1)
    }
    weeks.push(week)
  }
  return weeks
})

const heatmapMaxCount = computed(() => {
  let m = 1
  for (const e of props.dashboard.heatmap?.entries ?? []) {
    if (e.count > m) m = e.count
  }
  return m
})

function heatmapCellClass(count: number, future: boolean): string {
  if (future) return 'opacity-0 pointer-events-none'
  if (!count) return 'bg-muted/50 hover:ring-1 hover:ring-foreground/20'
  const ratio = count / heatmapMaxCount.value
  if (ratio <= 0.25) return 'bg-primary/25 hover:ring-1 hover:ring-primary'
  if (ratio <= 0.5) return 'bg-primary/50 hover:ring-1 hover:ring-primary'
  if (ratio <= 0.75) return 'bg-primary/75 hover:ring-1 hover:ring-primary'
  return 'bg-primary hover:ring-1 hover:ring-primary'
}

const activeTooltip = ref<{ text: string; x: number; y: number } | null>(null)
function showCellTooltip(
  e: MouseEvent,
  cell: { date: Date; key: string; count: number },
) {
  const dStr = formatIntl(cell.date, { day: 'numeric', month: 'short', year: 'numeric' })
  activeTooltip.value = {
    text: `${cell.count} on ${dStr}`,
    x: e.clientX,
    y: e.clientY - 30,
  }
}
function hideCellTooltip() {
  activeTooltip.value = null
}

// ── Chart logic ──
const graphData = computed(() => props.dashboard.graph)
const graphColors = [
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#ef4444',
  '#06b6d4',
  '#ec4899',
  '#84cc16',
  '#f97316',
  '#6366f1',
  '#14b8a6',
  '#a855f7',
]

// Series hidden by clicking their legend entry (indices into graph.datasets).
const hiddenSeries = ref(new Set<number>())
watch(
  () => props.dashboard.graph,
  () => { hiddenSeries.value = new Set() },
)
function toggleSeries(index: number) {
  const next = new Set(hiddenSeries.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  hiddenSeries.value = next
}

/** Tooltip value: money when the graph names a currency, else a localized number. */
function formatGraphValue(v: number): string {
  const code = graphData.value?.currency
  return code ? formatCurrency(v, code) : formatNumber(v, { maximumFractionDigits: 2 })
}
/** Axis value: compact (`125 тис.`) so large sums fit the gutter. */
function formatAxisValue(v: number): string {
  return formatNumber(v, { notation: 'compact', maximumFractionDigits: 1 })
}

function getSeriesColor(index: number): string {
  const custom = graphData.value?.colors
  if (custom && custom[index]) return custom[index]
  return graphColors[index % graphColors.length]
}

const chartContainerRef = ref<HTMLElement | null>(null)
const { width: containerWidth } = useElementSize(chartContainerRef)

/** Cap width so wide-screen charts don't look overly stretched. */
const chartWidth = computed(() => Math.min(900, Math.max(340, Math.round(containerWidth.value) || 700)))
const chartHeight = computed(() => graphData.value?.height || Math.round(chartWidth.value * 0.28))
const chartPadding = { top: 16, right: 28, bottom: 36, left: 48 }
const chartViewBox = computed(() => `0 0 ${chartWidth.value} ${chartHeight.value}`)

const chartPoints = computed(() => {
  const g = graphData.value
  if (!g || !g.labels.length || !g.datasets.length) return null

  const visible = g.datasets.map((_, i) => i).filter((i) => !hiddenSeries.value.has(i))
  const allVals = visible.flatMap((i) => g.datasets[i].values)
  const maxVal = Math.max(1, ...allVals)
  const minVal = 0
  const valRange = maxVal - minVal || 1

  const usableW = chartWidth.value - chartPadding.left - chartPadding.right
  const usableH = chartHeight.value - chartPadding.top - chartPadding.bottom

  const isBar = g.type === 'bar'
  const n = g.labels.length
  const xStep = isBar ? usableW / n : (n > 1 ? usableW / (n - 1) : usableW / 2)

  const numSeries = Math.max(1, visible.length)
  const barGap = 4
  const slotWidth = isBar ? Math.min(80, Math.max(24, xStep * 0.6)) : 20
  const singleBarWidth = isBar ? Math.max(8, Math.min(32, (slotWidth - (numSeries - 1) * barGap) / numSeries)) : 0
  const actualGroupWidth = numSeries * singleBarWidth + (numSeries - 1) * barGap

  const series = g.datasets.map((dataset, dsIdx) => {
    const slot = Math.max(0, visible.indexOf(dsIdx)) // position among visible bars
    const pts = dataset.values.map((v, i) => {
      const centerX = isBar
        ? chartPadding.left + i * xStep + xStep / 2
        : chartPadding.left + (n > 1 ? i * xStep : usableW / 2)
      const y = chartPadding.top + usableH - ((Math.max(0, v) - minVal) / valRange) * usableH
      const barX = centerX - actualGroupWidth / 2 + slot * (singleBarWidth + barGap)
      const barH = Math.max(0, chartPadding.top + usableH - y)

      return {
        x: centerX,
        y,
        barX,
        barW: singleBarWidth,
        barH,
        value: v,
        label: g.labels[i],
      }
    })
    return {
      name: dataset.name,
      color: getSeriesColor(dsIdx),
      hidden: hiddenSeries.value.has(dsIdx),
      pts,
      path: pts.length
        ? pts.reduce((acc, p, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)},${p.y.toFixed(1)}`, '')
        : '',
      areaPath: pts.length
        ? `${pts.reduce((acc, p, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)},${p.y.toFixed(1)}`, '')} L ${pts[pts.length - 1].x.toFixed(1)},${(chartPadding.top + usableH).toFixed(1)} L ${pts[0].x.toFixed(1)},${(chartPadding.top + usableH).toFixed(1)} Z`
        : '',
    }
  })

  // Horizontal guide lines
  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((pct) => ({
    y: chartPadding.top + usableH * (1 - pct),
    val: formatAxisValue(minVal + valRange * pct),
  }))

  const h = chartHeight.value
  const labelPositions = g.labels.map((lbl, i) => ({
    text: lbl,
    shortText: lbl.length > 13 ? lbl.slice(0, 12) + '…' : lbl,
    x: isBar ? chartPadding.left + i * xStep + xStep / 2 : chartPadding.left + (n > 1 ? i * xStep : usableW / 2),
    y: h - 10,
  }))

  return { series, gridLines, labelPositions, usableH, usableW }
})

// ── Transaction shortcuts logic ──
function getTransactionCount(doctype: string): { count?: number; openCount?: number; label: string } {
  const badge = props.dashboard.badges[doctype]
  if (badge) {
    return {
      count: badge.count,
      openCount: badge.open_count,
      label: badge.open_count !== undefined
        ? `${badge.open_count} / ${badge.count ?? 0}`
        : badge.count !== undefined
          ? String(badge.count)
          : '',
    }
  }
  return { label: '' }
}

function openTransactionList(linkDoctype: string) {
  const did = docId.value
  const query: Record<string, string> = {}
  if (did && doctypeName.value) {
    // Standard reverse filter convention
    query[`filter[${doctypeName.value.toLowerCase()}__eq]`] = did
  }
  router.push(appUrl({ name: linkDoctype, workspace: props.workspace, query }))
}

function createNewTransaction(linkDoctype: string) {
  const did = docId.value
  const preset: Record<string, unknown> = {}
  if (did && doctypeName.value) {
    preset[doctypeName.value.toLowerCase()] = did
  }
  emit('create-new', linkDoctype, preset, '')
}
</script>

<template>
  <div
    v-if="!dashboard.hidden"
    class="flex flex-col gap-3 rounded-lg border border-border/80 bg-card p-4 sm:p-5 shadow-xs transition-all"
  >
    <!-- 1. Headline Area -->
    <div
      v-if="dashboard.headline"
      :class="[
        'flex items-start justify-between gap-3 rounded-md border px-3.5 py-2.5 text-sm transition-all',
        resolveColorClasses(dashboard.headline.color).bg,
        resolveColorClasses(dashboard.headline.color).border,
        resolveColorClasses(dashboard.headline.color).text,
      ]"
    >
      <div class="flex items-center gap-2 min-w-0">
        <Info class="size-4 shrink-0 mt-0.5" />
        <div class="prose prose-sm dark:prose-invert max-w-none font-medium leading-relaxed" v-html="dashboard.headline.html" />
      </div>
      <Button
        v-if="!dashboard.headline.permanent"
        variant="ghost"
        size="icon-xs"
        class="shrink-0 -mr-1 text-inherit opacity-70 hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/10"
        :title="t('Dismiss')"
        @click="dismissHeadline"
      >
        <X class="size-3.5" />
      </Button>
    </div>

    <!-- 2. Comments / Alerts -->
    <div v-if="dashboard.comments.length" class="flex flex-col gap-2">
      <div
        v-for="(c, idx) in dashboard.comments"
        :key="idx"
        :class="[
          'flex items-start justify-between gap-3 rounded-md border px-3.5 py-2 text-sm',
          resolveColorClasses(c.color).bg,
          resolveColorClasses(c.color).border,
          resolveColorClasses(c.color).text,
        ]"
      >
        <div class="flex items-center gap-2 min-w-0">
          <AlertCircle class="size-4 shrink-0 mt-0.5" />
          <div class="prose prose-sm dark:prose-invert max-w-none leading-relaxed" v-html="c.html" />
        </div>
        <Button
          v-if="!c.permanent"
          variant="ghost"
          size="icon-xs"
          class="shrink-0 -mr-1 text-inherit opacity-70 hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/10"
          :title="t('Dismiss')"
          @click="dismissComment(idx)"
        >
          <X class="size-3.5" />
        </Button>
      </div>
    </div>

    <!-- 3. Document Status & Stat Indicators Area -->
    <div
      v-if="dashboard.docstatus_icon || dashboard.indicators.length"
      class="flex flex-wrap items-center gap-2 pt-0.5"
    >
      <!-- DocStatus Pill -->
      <Badge
        v-if="dashboard.docstatus_icon"
        variant="outline"
        class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider rounded-md border"
        :class="[
          dashboard.docstatus_icon === 'Draft' ? 'border-border bg-muted/60 text-muted-foreground' :
          dashboard.docstatus_icon === 'Submitted' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' :
          dashboard.docstatus_icon === 'Cancelled' ? 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-400' :
          'border-primary/40 bg-primary/10 text-primary'
        ]"
      >
        <span
          class="size-1.5 rounded-full animate-pulse"
          :class="[
            dashboard.docstatus_icon === 'Draft' ? 'bg-muted-foreground' :
            dashboard.docstatus_icon === 'Submitted' ? 'bg-emerald-500' :
            dashboard.docstatus_icon === 'Cancelled' ? 'bg-rose-500' :
            'bg-primary'
          ]"
        />
        {{ dashboard.docstatus_icon }}
      </Badge>

      <!-- Stat Indicators -->
      <div
        v-for="(ind, i) in dashboard.indicators"
        :key="i"
        class="inline-flex items-center gap-2 rounded-full border px-3 py-0.5 text-xs font-medium transition-colors"
        :class="[
          resolveColorClasses(ind.color).bg,
          resolveColorClasses(ind.color).border,
          resolveColorClasses(ind.color).text,
        ]"
      >
        <span class="size-2 rounded-full" :class="resolveColorClasses(ind.color).dot" />
        <span>{{ ind.label }}</span>
      </div>
    </div>

    <!-- 4. Progress Bars Area -->
    <div v-if="dashboard.progress.length" class="flex flex-col gap-3 py-1">
      <div
        v-for="(p, pi) in dashboard.progress"
        :key="pi"
        class="flex flex-col gap-1.5"
      >
        <div class="flex items-center justify-between text-xs font-medium">
          <span class="text-foreground font-semibold">{{ p.title }}</span>
          <span class="text-muted-foreground">
            {{ p.message || `${Math.round(p.segments.reduce((acc, s) => acc + s.width, 0))}%` }}
          </span>
        </div>

        <!-- Multi-segment progress bar track -->
        <div class="h-2 w-full overflow-hidden rounded-full bg-muted/70 flex">
          <div
            v-for="(seg, si) in p.segments"
            :key="si"
            class="h-full transition-all duration-500 ease-out"
            :class="resolveProgressSegmentColor(seg.color)"
            :style="{
              width: `${seg.width}%`,
              backgroundColor: seg.color && (seg.color.startsWith('#') || seg.color.startsWith('rgb')) ? seg.color : undefined
            }"
            :title="seg.title ? `${seg.title}: ${seg.width}%` : `${seg.width}%`"
          />
        </div>
      </div>
    </div>

    <!-- 5. Chart Area -->
    <div
      v-if="dashboard.graph && chartPoints"
      class="flex flex-col gap-2 rounded-lg border border-border/70 bg-background/50 p-3 sm:p-4"
    >
      <div class="flex items-center justify-between">
        <h4 v-if="dashboard.graph.title" class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {{ dashboard.graph.title }}
        </h4>
        <!-- Legend -->
        <div class="flex flex-wrap items-center gap-3 text-xs ml-auto">
          <button
            v-for="(ds, di) in chartPoints.series"
            :key="di"
            type="button"
            class="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
            :class="{ 'opacity-50 line-through': ds.hidden }"
            :aria-pressed="!ds.hidden"
            :title="ds.hidden ? t('Show') : t('Hide')"
            @click="toggleSeries(di)"
          >
            <span class="size-2 rounded-full" :style="{ backgroundColor: ds.color }" />
            <span>{{ ds.name }}</span>
          </button>
        </div>
      </div>

      <!-- Responsive SVG Chart (scrolls horizontally on narrow screens) -->
      <div class="w-full overflow-x-auto pb-1">
        <div ref="chartContainerRef" class="w-full" style="min-width: 320px">
        <svg
          class="w-full overflow-visible select-none"
          :style="{ height: `${chartHeight}px` }"
          :viewBox="chartViewBox"
        >
          <defs>
            <linearGradient
              v-for="(ds, di) in chartPoints.series"
              :key="`grad-${di}`"
              :id="`area-grad-${di}`"
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop offset="0%" :stop-color="ds.color" stop-opacity="0.25" />
              <stop offset="100%" :stop-color="ds.color" stop-opacity="0.0" />
            </linearGradient>
          </defs>

          <!-- Grid Lines -->
          <g class="stroke-border/60 stroke-[0.8]" stroke-dasharray="3 3">
            <line
              v-for="(gl, gi) in chartPoints.gridLines"
              :key="gi"
              :x1="chartPadding.left"
              :y1="gl.y"
              :x2="chartWidth - chartPadding.right"
              :y2="gl.y"
            />
          </g>

          <!-- Y Axis Labels -->
          <g class="fill-muted-foreground text-[10px]" text-anchor="end">
            <text
              v-for="(gl, gi) in chartPoints.gridLines"
              :key="gi"
              :x="chartPadding.left - 6"
              :y="gl.y + 3"
            >
              {{ gl.val }}
            </text>
          </g>

          <!-- Bar Chart Type -->
          <template v-if="dashboard.graph.type === 'bar'">
            <g v-for="(ds, di) in chartPoints.series" v-show="!ds.hidden" :key="`bars-${di}`">
              <rect
                v-for="(p, pi) in ds.pts"
                :key="`bar-${pi}`"
                :x="p.barX"
                :y="p.y"
                :width="p.barW"
                :height="p.barH"
                :fill="ds.color"
                rx="3"
                class="transition-all hover:opacity-80"
              >
                <title>{{ `${ds.name} (${p.label}): ${formatGraphValue(p.value)}` }}</title>
              </rect>
            </g>
          </template>

          <!-- Line / Area Chart Type -->
          <template v-else>
            <!-- Area Fill (only for type 'area'; 'line' is a bare stroke) -->
            <template v-if="dashboard.graph.type === 'area'">
              <path
                v-for="(ds, di) in chartPoints.series"
                v-show="!ds.hidden"
                :key="`area-${di}`"
                :d="ds.areaPath"
                :fill="`url(#area-grad-${di})`"
              />
            </template>

            <!-- Stroke Path -->
            <path
              v-for="(ds, di) in chartPoints.series"
              v-show="!ds.hidden"
              :key="`line-${di}`"
              :d="ds.path"
              fill="none"
              :stroke="ds.color"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />

            <!-- Data Dots -->
            <g v-for="(ds, di) in chartPoints.series" v-show="!ds.hidden" :key="`dots-${di}`">
              <circle
                v-for="(p, pi) in ds.pts"
                :key="`dot-${pi}`"
                :cx="p.x"
                :cy="p.y"
                r="3.5"
                :fill="ds.color"
                class="stroke-background stroke-2 transition-transform hover:scale-150 cursor-pointer"
              >
                <title>{{ `${ds.name} (${p.label}): ${formatGraphValue(p.value)}` }}</title>
              </circle>
            </g>
          </template>

          <!-- X Axis Labels -->
          <g class="fill-muted-foreground text-[10px]" text-anchor="middle">
            <text
              v-for="(item, li) in chartPoints.labelPositions"
              :key="li"
              :x="item.x"
              :y="item.y"
            >
              {{ item.shortText }}
              <title>{{ item.text }}</title>
            </text>
          </g>
        </svg>
        </div>
      </div>
    </div>

    <!-- 6. Heatmap Area -->
    <div
      v-if="dashboard.heatmap"
      class="flex flex-col gap-2 rounded-lg border border-border/70 bg-background/50 p-3 sm:p-4"
    >
      <div class="flex items-center justify-between">
        <h4 v-if="dashboard.heatmap.title" class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {{ dashboard.heatmap.title }}
        </h4>
        <div class="flex items-center gap-1.5 text-[10px] text-muted-foreground ml-auto">
          <span>{{ t('Less') }}</span>
          <span class="size-2.5 rounded-xs bg-muted/50" />
          <span class="size-2.5 rounded-xs bg-primary/25" />
          <span class="size-2.5 rounded-xs bg-primary/50" />
          <span class="size-2.5 rounded-xs bg-primary/75" />
          <span class="size-2.5 rounded-xs bg-primary" />
          <span>{{ t('More') }}</span>
        </div>
      </div>

      <!-- Calendar Activity Grid -->
      <div class="w-full overflow-x-auto pb-1">
        <div class="inline-flex gap-1 py-1">
          <div
            v-for="(week, wi) in heatmapWeeks"
            :key="wi"
            class="flex flex-col gap-1"
          >
            <div
              v-for="(cell, di) in week"
              :key="di"
              class="size-3 rounded-xs transition-colors cursor-pointer"
              :class="heatmapCellClass(cell.count, cell.future)"
              @mouseenter="showCellTooltip($event, cell)"
              @mouseleave="hideCellTooltip"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- 7. Transactions Area (Related Documents) -->
    <div
      v-if="dashboard.transactions.length"
      class="flex flex-col gap-2.5 pt-1"
    >
      <div
        v-for="(group, gi) in dashboard.transactions"
        :key="gi"
        class="flex flex-col gap-1.5"
      >
        <span
          v-if="group.label"
          class="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80 px-0.5"
        >
          {{ group.label }}
        </span>

        <div class="flex flex-wrap gap-2">
          <div
            v-for="item in group.items"
            :key="item"
            class="inline-flex items-center rounded-lg border border-border/80 bg-background/80 overflow-hidden text-xs shadow-2xs hover:border-primary/50 transition-colors"
          >
            <button
              type="button"
              class="flex items-center gap-2 px-3 py-1.5 font-medium text-foreground hover:text-primary transition-colors cursor-pointer"
              @click="openTransactionList(item)"
            >
              <FileText class="size-3 text-muted-foreground" />
              <span>{{ item }}</span>
              <Badge
                v-if="getTransactionCount(item).label"
                variant="secondary"
                class="font-mono text-[10px] h-4.5 px-1.5 min-w-[18px] flex items-center justify-center bg-muted/60 border-none"
              >
                {{ getTransactionCount(item).label }}
              </Badge>
              <ArrowUpRight class="size-3 text-muted-foreground/40" />
            </button>

            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              class="h-7 w-7 border-l border-border/60 text-muted-foreground hover:text-foreground rounded-none"
              :title="t('New {doctype}', { doctype: item })"
              :aria-label="t('New {doctype}', { doctype: item })"
              @click="createNewTransaction(item)"
            >
              <Plus class="size-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </div>

    <!-- 8. Custom HTML Sections Area -->
    <template v-if="dashboard.sections.length">
      <div
        v-for="section in dashboard.sections.filter((s) => !s.hidden)"
        :key="section.name"
        :class="['rounded-md border border-border/70 bg-background/40 p-3.5', section.css_class || '']"
      >
        <h4
          v-if="section.label"
          class="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2"
        >
          {{ section.label }}
        </h4>
        <div class="prose prose-sm dark:prose-invert max-w-none" v-html="section.html" />
      </div>
    </template>

    <!-- Floating Tooltip for Heatmap -->
    <div
      v-if="activeTooltip"
      class="fixed pointer-events-none z-50 rounded bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md border border-border/80 -translate-x-1/2"
      :style="{ left: `${activeTooltip.x}px`, top: `${activeTooltip.y}px` }"
    >
      {{ activeTooltip.text }}
    </div>
  </div>
</template>
