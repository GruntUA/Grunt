<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, shallowRef, triggerRef, computed, onMounted, watch, nextTick } from 'vue'
import {
  getLocalTimeZone,
  isWeekend,
  startOfMonth,
  startOfWeek,
  today,
  type CalendarDate,
} from '@internationalized/date'
import { useRouter } from 'vue-router'
import { docUrl } from '@/core/workspaceUrl'
import type { DocType } from '@/types'
import {
  daysBetween,
  eachDate,
  formatCalendarDate,
  formatMonthYear,
  isoWeek,
  localeTag,
  toCalendarDay,
} from '@/core/datetime'
import { docsApi } from '@/core/api/docs'
import { useToast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { ChartGantt, ChevronLeft, ChevronRight } from '@lucide/vue'
import { ButtonGroup } from '@/components/ui/button-group'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { isDateType } from '@/core/fieldRegistry'

const { t } = useI18n()

const props = defineProps<{
  doctype: DocType
  workspace?: string
  activeFilters?: unknown[]
  quickFilterValues?: Record<string, string>
  refreshKey?: number
}>()

const router = useRouter()
const toast = useToast()

// Config (assembled from the flat gantt_* fields)
const cfg = computed(() => ({
  start_field: props.doctype.gantt_start_field ?? '',
  end_field: props.doctype.gantt_end_field ?? '',
  title_field: props.doctype.gantt_title_field ?? '',
  progress_field: props.doctype.gantt_progress_field ?? '',
  color_field: props.doctype.gantt_color_field ?? '',
  color_map: props.doctype.gantt_color_map ?? {},
  default_color: props.doctype.gantt_default_color ?? '',
  dependencies_field: props.doctype.gantt_dependencies_field ?? '',
}))
const startField = computed(() => cfg.value?.start_field || autoDates.value[0] || '')
const endField = computed(() => cfg.value?.end_field || autoDates.value[1] || '')
const titleField = computed(() => cfg.value?.title_field || props.doctype.title_field || 'name')
const progressField = computed(() => cfg.value?.progress_field || '')
const colorField = computed(() => cfg.value?.color_field || '')
const colorMap = computed(() => cfg.value?.color_map || {})
const defaultColor = computed(() => cfg.value?.default_color || 'var(--primary)')
const depsField = computed(() => cfg.value?.dependencies_field || '')

const autoDates = computed(() =>
  props.doctype.fields
    .filter((f) => isDateType(f.fieldtype))
    .map((f) => f.fieldname),
)
const isConfigured = computed(() => !!startField.value && !!endField.value)
const fieldType = (name: string) =>
  props.doctype.fields.find((f) => f.fieldname === name)?.fieldtype ?? 'Date'

// Zoom
type Zoom = 'day' | 'week' | 'month'
const zoom = ref<Zoom>('week')
const DAY_WIDTH: Record<Zoom, number> = { day: 34, week: 16, month: 5 }
const dayWidth = computed(() => DAY_WIDTH[zoom.value])
const ROW_H = 38
const HEADER_H = 52

// Data
interface GanttTask {
  id: string
  name: string
  title: string
  start: CalendarDate
  end: CalendarDate
  progress: number
  color: string
  deps: string[]
}

// shallowRef: CalendarDate is an immutable value - no deep proxies; mutations call triggerRef.
const tasks = shallowRef<GanttTask[]>([])
const isLoading = ref(true)
const scrollEl = ref<HTMLElement | null>(null)

function resolveColor(row: Record<string, unknown>): string {
  if (colorField.value) {
    const v = String(row[colorField.value] ?? '')
    if (colorMap.value[v]) return colorMap.value[v]
  }
  return defaultColor.value
}

async function load() {
  if (!isConfigured.value) {
    tasks.value = []
    isLoading.value = false
    return
  }
  isLoading.value = true
  try {
    const wanted = new Set([
      'name',
      startField.value,
      endField.value,
      titleField.value,
      progressField.value,
      colorField.value,
      depsField.value,
    ])
    wanted.delete('')
    const resp = await docsApi.list(props.doctype.name, {
      filters: (props.activeFilters as never) ?? [],
      quickFilters: props.quickFilterValues ?? {},
      fields: [...wanted].join(','),
      per_page: 500,
    })
    const rows = (resp.data ?? []) as Record<string, unknown>[]
    const out: GanttTask[] = []
    for (const row of rows) {
      const rawStart = row[startField.value]
      const rawEnd = row[endField.value]
      if (!rawStart || !rawEnd) continue
      const start = toCalendarDay(rawStart)
      let end = toCalendarDay(rawEnd)
      if (!start || !end) continue
      if (end.compare(start) < 0) end = start
      const rawProg = progressField.value ? Number(row[progressField.value]) : 0
      const progress = Number.isFinite(rawProg)
        ? Math.max(0, Math.min(100, rawProg <= 1 && rawProg > 0 ? rawProg * 100 : rawProg))
        : 0
      out.push({
        id: String(row.id ?? row.name),
        name: String(row.name),
        title: String(row[titleField.value] || row.name || row.id),
        start,
        end,
        progress,
        color: resolveColor(row),
        deps: depsField.value
          ? String(row[depsField.value] ?? '')
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
      })
    }
    out.sort((a, b) => a.start.compare(b.start))
    tasks.value = out
  } catch (e) {
    console.error('Gantt: failed to load', e)
    toast.error(t('Could not load Gantt chart data'))
  } finally {
    isLoading.value = false
  }
}

onMounted(async () => {
  await load()
  await nextTick()
  scrollToToday()
})
watch(() => props.refreshKey, (_v, old) => { if (old !== undefined) load() })
watch([() => props.activeFilters, () => props.quickFilterValues], load, { deep: true })
watch(() => props.doctype.name, load)

// Timeline range
const range = computed(() => {
  const now = todayDate()
  if (!tasks.value.length) {
    return { start: now.subtract({ days: 14 }), end: now.add({ days: 30 }) }
  }
  let lo = now
  let hi = now
  for (const task of tasks.value) {
    if (task.start.compare(lo) < 0) lo = task.start
    if (task.end.compare(hi) > 0) hi = task.end
  }
  return { start: lo.subtract({ days: 7 }), end: hi.add({ days: 14 }) }
})

const totalDays = computed(() => daysBetween(range.value.start, range.value.end) + 1)
const chartWidth = computed(() => totalDays.value * dayWidth.value)
const chartHeight = computed(() => Math.max(tasks.value.length * ROW_H, ROW_H * 3))

function todayDate(): CalendarDate {
  return today(getLocalTimeZone())
}
function xFor(d: CalendarDate): number {
  return daysBetween(range.value.start, d) * dayWidth.value
}
function rowMid(i: number): number {
  return i * ROW_H + ROW_H / 2
}

// Header ticks
interface Tick { x: number; label: string; sub?: string; width: number }
const ticks = computed<Tick[]>(() => {
  const { start, end } = range.value
  if (zoom.value === 'day') {
    return eachDate(start, end).map((d) => ({
      x: xFor(d),
      label: String(d.day),
      sub: formatCalendarDate(d, { weekday: 'short' }),
      width: dayWidth.value,
    }))
  }
  if (zoom.value === 'week') {
    return eachDate(startOfWeek(start, localeTag(), 'mon'), end, { weeks: 1 }).map((d) => ({
      x: xFor(d),
      label: formatCalendarDate(d, { day: 'numeric', month: 'short' }),
      sub: `${t('wk.')}${isoWeek(d)}`,
      width: dayWidth.value * 7,
    }))
  }
  return eachDate(startOfMonth(start), end, { months: 1 }).map((d) => ({
    x: xFor(d),
    label: formatMonthYear(d),
    width: dayWidth.value * 31,
  }))
})

const gridLines = computed(() => ticks.value.map((t) => t.x))
const todayX = computed(() => xFor(todayDate()))
const showToday = computed(() => todayX.value >= 0 && todayX.value <= chartWidth.value)

const weekendBands = computed(() => {
  if (zoom.value !== 'day') return [] as number[]
  return eachDate(range.value.start, range.value.end)
    .filter((d) => isWeekend(d, localeTag()))
    .map((d) => xFor(d))
})

const LEFT_COL_W = 256
function scrollToToday() {
  if (!scrollEl.value) return
  const target = Math.max(0, todayX.value + LEFT_COL_W - scrollEl.value.clientWidth / 3)
  scrollEl.value.scrollTo({ left: target, behavior: 'smooth' })
}
function nudge(dir: number) {
  scrollEl.value?.scrollBy({ left: dir * 320, behavior: 'smooth' })
}

// Dependency arrows
const arrows = computed(() => {
  if (!depsField.value) return [] as { d: string; head: string }[]
  const byName = new Map(tasks.value.map((t, i) => [t.name, { t, i }]))
  const out: { d: string; head: string }[] = []
  tasks.value.forEach((task, i) => {
    for (const depName of task.deps) {
      const dep = byName.get(depName)
      if (!dep) continue
      const x1 = xFor(dep.t.end) + dayWidth.value
      const y1 = rowMid(dep.i)
      const x2 = xFor(task.start)
      const y2 = rowMid(i)
      const midX = Math.max(x1 + 10, x2 - 10)
      out.push({
        d: `M ${x1} ${y1} H ${midX} V ${y2} H ${x2}`,
        head: `M ${x2 - 6} ${y2 - 4} L ${x2} ${y2} L ${x2 - 6} ${y2 + 4}`,
      })
    }
  })
  return out
})

// Drag to reschedule
type DragMode = 'move' | 'resize-start' | 'resize-end'
interface DragState {
  id: string
  mode: DragMode
  originX: number
  deltaDays: number
  raw: { start: unknown; end: unknown }
}
const drag = ref<DragState | null>(null)
const isSaving = ref(false)

function barStyle(task: GanttTask, i: number) {
  let s = task.start
  let e = task.end
  if (drag.value?.id === task.id) {
    const dd = drag.value.deltaDays
    if (drag.value.mode === 'move') { s = s.add({ days: dd }); e = e.add({ days: dd }) }
    else if (drag.value.mode === 'resize-start') s = s.add({ days: dd })
    else e = e.add({ days: dd })
    if (e.compare(s) < 0) { if (drag.value.mode === 'resize-start') s = e; else e = s }
  }
  const left = xFor(s)
  const width = Math.max((daysBetween(s, e) + 1) * dayWidth.value, dayWidth.value)
  return {
    transform: `translateX(${left}px)`,
    width: `${width}px`,
    top: `${i * ROW_H + 7}px`,
    background: task.color,
  }
}

function onBarPointerDown(e: PointerEvent, task: GanttTask, mode: DragMode) {
  if (e.button !== 0) return
  e.stopPropagation()
  ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  drag.value = {
    id: task.id,
    mode,
    originX: e.clientX,
    deltaDays: 0,
    raw: { start: rawOf(task, 'start'), end: rawOf(task, 'end') },
  }
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd, { once: true })
}

function onDragMove(e: PointerEvent) {
  if (!drag.value) return
  drag.value.deltaDays = Math.round((e.clientX - drag.value.originX) / dayWidth.value)
}

async function onDragEnd() {
  window.removeEventListener('pointermove', onDragMove)
  const d = drag.value
  if (!d) return
  const dd = d.deltaDays
  drag.value = null
  if (!dd) return
  const task = tasks.value.find((t) => t.id === d.id)
  if (!task) return

  const patch: Record<string, string> = {}
  if (d.mode === 'move' || d.mode === 'resize-start') {
    const ns = task.start.add({ days: dd })
    patch[startField.value] = serialize(ns, d.raw.start, fieldType(startField.value))
  }
  if (d.mode === 'move' || d.mode === 'resize-end') {
    const ne = task.end.add({ days: dd })
    patch[endField.value] = serialize(ne, d.raw.end, fieldType(endField.value))
  }

  // optimistic
  if (d.mode === 'move') { task.start = task.start.add({ days: dd }); task.end = task.end.add({ days: dd }) }
  else if (d.mode === 'resize-start') task.start = task.start.add({ days: dd })
  else task.end = task.end.add({ days: dd })
  if (task.end.compare(task.start) < 0) task.end = task.start
  triggerRef(tasks)

  try {
    isSaving.value = true
    await docsApi.update(props.doctype.name, task.id, patch)
  } catch (e) {
    console.error('Gantt: reschedule failed', e)
    toast.error(t('Could not update dates'))
    await load()
  } finally {
    isSaving.value = false
  }
}

function rawOf(task: GanttTask, which: 'start' | 'end'): string {
  return `${task[which].toString()}T00:00:00`
}
function serialize(d: CalendarDate, original: unknown, ftype: string): string {
  const day = d.toString()
  if (ftype !== 'Datetime') return day
  const orig = String(original ?? '')
  const timePart = orig.includes('T') ? orig.split('T')[1] : orig.slice(11) || '00:00:00'
  return `${day}T${timePart || '00:00:00'}`
}

function openTask(task: GanttTask) {
  if (drag.value) return
  router.push(docUrl(props.doctype.name, task.id, props.workspace))
}

function fmtSpan(task: GanttTask) {
  const short = (d: CalendarDate) => formatCalendarDate(d, { day: '2-digit', month: '2-digit', year: '2-digit' })
  return `${short(task.start)} → ${short(task.end)}`
}

const zoomOptions: { value: Zoom; label: string }[] = [
  { value: 'day', label: t('Days') },
  { value: 'week', label: t('Weeks') },
  { value: 'month', label: t('Months') },
]
</script>

<template>
  <div class="flex flex-col h-full bg-card border border-border/60 rounded-lg overflow-hidden">
    <!-- Toolbar -->
    <div class="flex items-center justify-between gap-3 p-3 border-b border-border/40 bg-muted/20">
      <div class="flex items-center gap-2">
        <div class="size-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
          <ChartGantt class="size-4 text-primary" />
        </div>
        <h2 class="text-base font-semibold text-foreground">{{ t('Gantt chart') }}</h2>
        <span v-if="isSaving" class="text-primary animate-pulse">{{ t('Updating…') }}</span>
      </div>

      <div class="flex items-center gap-2">
        <ToggleGroup type="single" variant="outline" size="sm" :model-value="zoom"
          @update:model-value="(v) => v && (zoom = v as typeof zoom)">
          <ToggleGroupItem v-for="opt in zoomOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</ToggleGroupItem>
        </ToggleGroup>
        <ButtonGroup>
          <Button variant="outline" size="icon-sm" :aria-label="t('Previous')" @click="nudge(-1)"><ChevronLeft /></Button>
          <Button variant="outline" size="sm" @click="scrollToToday">{{ t('Today') }}</Button>
          <Button variant="outline" size="icon-sm" :aria-label="t('Next')" @click="nudge(1)"><ChevronRight /></Button>
        </ButtonGroup>
        <Spinner v-if="isLoading" />
      </div>
    </div>

    <!-- Not configured -->
    <div v-if="!isConfigured" class="flex-1 flex flex-col items-center justify-center gap-2 p-10 text-center text-muted-foreground">
      <ChartGantt class="size-8 opacity-40" />
      <p>{{ t('The Gantt chart needs start and end fields (Date/Datetime).') }}</p>
      <p>{{ t('Choose them in the Builder → «Views» tab → «Gantt chart».') }}</p>
    </div>

    <!-- Chart -->
    <div v-else ref="scrollEl" class="flex-1 min-h-0 overflow-auto custom-scrollbar relative">
      <div class="flex" :style="{ width: `${chartWidth + 256}px` }">
        <!-- Frozen task column -->
        <div class="sticky left-0 z-30 shrink-0 w-64 border-r border-border/40 bg-card">
          <div class="sticky top-0 z-40 border-b border-border/40 bg-card px-3 flex items-end pb-2 font-semibold text-muted-foreground uppercase tracking-wider"
            :style="{ height: `${HEADER_H}px` }">
            {{ props.doctype.label }}
          </div>
          <div v-if="!isLoading && !tasks.length" class="p-4 text-muted-foreground">
            {{ t('No documents with dates filled in.') }}
          </div>
          <div v-for="task in tasks" :key="task.id"
            class="flex items-center gap-2 px-3 border-b border-border/20 cursor-pointer hover:bg-muted/40 transition-colors"
            :style="{ height: `${ROW_H}px` }" @click="openTask(task)">
            <span class="size-2 rounded-full shrink-0" :style="{ background: task.color }" />
            <span class="truncate text-sm text-foreground" :title="task.title">{{ task.title }}</span>
          </div>
        </div>

        <!-- Timeline -->
        <div class="relative" :style="{ width: `${chartWidth}px` }">
          <!-- Header -->
          <div class="sticky top-0 z-20 bg-card/95 backdrop-blur border-b border-border/40"
            :style="{ height: `${HEADER_H}px` }">
            <div v-for="(t, i) in ticks" :key="i"
              class="absolute top-0 h-full border-l border-border/40 flex flex-col justify-end pb-1.5 px-1.5 overflow-hidden"
              :style="{ transform: `translateX(${t.x}px)`, width: `${t.width}px` }">
              <span class="text-[11px] font-semibold text-foreground leading-none truncate">{{ t.label }}</span>
              <span v-if="t.sub" class="text-[10px] text-muted-foreground leading-none mt-0.5 truncate">{{ t.sub }}</span>
            </div>
          </div>

          <!-- Body -->
          <div class="relative" :style="{ height: `${chartHeight}px` }">
            <!-- weekend bands -->
            <div v-for="(x, i) in weekendBands" :key="'wb' + i"
              class="absolute top-0 bottom-0 bg-muted/25 pointer-events-none"
              :style="{ transform: `translateX(${x}px)`, width: `${dayWidth}px` }" />
            <!-- grid lines -->
            <div v-for="(x, i) in gridLines" :key="'gl' + i"
              class="absolute top-0 bottom-0 border-l border-border/25 pointer-events-none"
              :style="{ transform: `translateX(${x}px)` }" />
            <!-- row separators -->
            <div v-for="(task, i) in tasks" :key="'rs' + task.id"
              class="absolute left-0 right-0 border-b border-border/15 pointer-events-none"
              :style="{ top: `${(i + 1) * ROW_H}px` }" />
            <!-- today -->
            <div v-if="showToday" class="absolute top-0 bottom-0 w-px bg-primary/70 z-10 pointer-events-none"
              :style="{ transform: `translateX(${todayX}px)` }">
              <span class="absolute -top-0 -translate-x-1/2 size-1.5 rounded-full bg-primary" />
            </div>

            <!-- dependency arrows -->
            <svg v-if="arrows.length" class="absolute inset-0 w-full h-full pointer-events-none z-[5]" :width="chartWidth" :height="chartHeight">
              <g fill="none" stroke="var(--muted-foreground)" stroke-width="1.5" opacity="0.55">
                <path v-for="(a, i) in arrows" :key="'a' + i" :d="a.d" />
                <path v-for="(a, i) in arrows" :key="'h' + i" :d="a.head" stroke-linejoin="round" />
              </g>
            </svg>

            <!-- bars -->
            <div v-for="(task, i) in tasks" :key="task.id"
              class="absolute h-6 rounded-md shadow-sm ring-1 ring-black/5 flex items-center overflow-hidden group cursor-grab active:cursor-grabbing select-none"
              :style="barStyle(task, i)"
              @pointerdown="onBarPointerDown($event, task, 'move')"
              @click="openTask(task)">
              <span v-if="task.progress > 0" class="absolute inset-y-0 left-0 bg-black/25"
                :style="{ width: `${task.progress}%` }" />
              <span class="relative px-2 text-[11px] font-medium text-white truncate drop-shadow-sm">
                {{ task.title }}<template v-if="task.progress > 0"> · {{ Math.round(task.progress) }}%</template>
              </span>
              <span class="absolute inset-y-0 left-0 w-1.5 cursor-ew-resize opacity-0 group-hover:opacity-100 bg-white/40"
                @pointerdown.stop="onBarPointerDown($event, task, 'resize-start')" />
              <span class="absolute inset-y-0 right-0 w-1.5 cursor-ew-resize opacity-0 group-hover:opacity-100 bg-white/40"
                @pointerdown.stop="onBarPointerDown($event, task, 'resize-end')" />
              <span class="pointer-events-none absolute left-0 -bottom-4 hidden group-hover:block text-[10px] text-muted-foreground whitespace-nowrap">
                {{ fmtSpan(task) }}
              </span>
            </div>

            <div v-if="!isLoading && !tasks.length"
              class="absolute inset-0 flex items-center justify-center text-muted-foreground">
              {{ t('No documents with start and end dates filled in.') }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 8px; height: 8px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 10px;
  border: 2px solid transparent;
  background-clip: padding-box;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background-color: var(--muted-foreground); }
</style>
