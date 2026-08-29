<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import {
  format,
  parseISO,
  startOfDay,
  addDays,
  differenceInCalendarDays,
  eachDayOfInterval,
  eachWeekOfInterval,
  eachMonthOfInterval,
  isWeekend,
  min as minDate,
  max as maxDate,
} from 'date-fns'
import { uk, enUS } from 'date-fns/locale'
import { useRouter } from 'vue-router'
import type { DocType } from '@/types'
import { siteConfigState } from '@/core/composables/useSiteConfig'
import { docsApi } from '@/core/api/docs'
import { useToast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { ChartGantt, ChevronLeft, ChevronRight } from '@lucide/vue'

const props = defineProps<{
  doctype: DocType
  workspace?: string
  activeFilters?: unknown[]
  fastFilterValues?: Record<string, string>
  refreshKey?: number
}>()

const router = useRouter()
const toast = useToast()
const dfLocale = computed(() => (siteConfigState().language.toLowerCase().startsWith('en') ? enUS : uk))

// ── Config ────────────────────────────────────────────────────────────────
const cfg = computed(() => props.doctype.gantt_view ?? null)
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
    .filter((f) => f.fieldtype === 'Date' || f.fieldtype === 'Datetime')
    .map((f) => f.fieldname),
)
const isConfigured = computed(() => !!startField.value && !!endField.value)
const fieldType = (name: string) =>
  props.doctype.fields.find((f) => f.fieldname === name)?.fieldtype ?? 'Date'

// ── Zoom ──────────────────────────────────────────────────────────────────
type Zoom = 'day' | 'week' | 'month'
const zoom = ref<Zoom>('week')
const DAY_WIDTH: Record<Zoom, number> = { day: 34, week: 16, month: 5 }
const dayWidth = computed(() => DAY_WIDTH[zoom.value])
const ROW_H = 38
const HEADER_H = 52

// ── Data ──────────────────────────────────────────────────────────────────
interface GanttTask {
  id: string
  name: string
  title: string
  start: Date
  end: Date
  progress: number
  color: string
  deps: string[]
}

const tasks = ref<GanttTask[]>([])
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
      fastFilters: props.fastFilterValues ?? {},
      fields: [...wanted].join(','),
      per_page: 500,
    })
    const rows = (resp.data ?? []) as Record<string, unknown>[]
    const out: GanttTask[] = []
    for (const row of rows) {
      const rawStart = row[startField.value]
      const rawEnd = row[endField.value]
      if (!rawStart || !rawEnd) continue
      const start = startOfDay(parseISO(String(rawStart).slice(0, 19)))
      let end = startOfDay(parseISO(String(rawEnd).slice(0, 19)))
      if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) continue
      if (end < start) end = start
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
    out.sort((a, b) => a.start.getTime() - b.start.getTime())
    tasks.value = out
  } catch (e) {
    console.error('Gantt: failed to load', e)
    toast.error('Не вдалося завантажити дані для діаграми Ганта')
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
watch([() => props.activeFilters, () => props.fastFilterValues], load, { deep: true })
watch(() => props.doctype.name, load)

// ── Timeline range ────────────────────────────────────────────────────────
const range = computed(() => {
  const today = startOfDay(new Date())
  if (!tasks.value.length) {
    return { start: addDays(today, -14), end: addDays(today, 30) }
  }
  const starts = tasks.value.map((t) => t.start)
  const ends = tasks.value.map((t) => t.end)
  const lo = minDate([...starts, today])
  const hi = maxDate([...ends, today])
  return { start: addDays(startOfDay(lo), -7), end: addDays(startOfDay(hi), 14) }
})

const totalDays = computed(() => differenceInCalendarDays(range.value.end, range.value.start) + 1)
const chartWidth = computed(() => totalDays.value * dayWidth.value)
const chartHeight = computed(() => Math.max(tasks.value.length * ROW_H, ROW_H * 3))

function xFor(d: Date): number {
  return differenceInCalendarDays(startOfDay(d), range.value.start) * dayWidth.value
}
function rowMid(i: number): number {
  return i * ROW_H + ROW_H / 2
}

// ── Header ticks ──────────────────────────────────────────────────────────
interface Tick { x: number; label: string; sub?: string; width: number }
const ticks = computed<Tick[]>(() => {
  const { start, end } = range.value
  if (zoom.value === 'day') {
    return eachDayOfInterval({ start, end }).map((d) => ({
      x: xFor(d),
      label: format(d, 'd', { locale: dfLocale.value }),
      sub: format(d, 'EEEEEE', { locale: dfLocale.value }),
      width: dayWidth.value,
    }))
  }
  if (zoom.value === 'week') {
    return eachWeekOfInterval({ start, end }, { weekStartsOn: 1 }).map((d) => ({
      x: xFor(d),
      label: format(d, 'd MMM', { locale: dfLocale.value }),
      sub: format(d, "'т.'w", { locale: dfLocale.value }),
      width: dayWidth.value * 7,
    }))
  }
  return eachMonthOfInterval({ start, end }).map((d) => ({
    x: xFor(d),
    label: format(d, 'LLLL yyyy', { locale: dfLocale.value }),
    width: dayWidth.value * 31,
  }))
})

const gridLines = computed(() => ticks.value.map((t) => t.x))
const todayX = computed(() => xFor(new Date()))
const showToday = computed(() => todayX.value >= 0 && todayX.value <= chartWidth.value)

const weekendBands = computed(() => {
  if (zoom.value !== 'day') return [] as number[]
  return eachDayOfInterval(range.value)
    .filter((d) => isWeekend(d))
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

// ── Dependency arrows ─────────────────────────────────────────────────────
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

// ── Drag to reschedule ────────────────────────────────────────────────────
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
    if (drag.value.mode === 'move') { s = addDays(s, dd); e = addDays(e, dd) }
    else if (drag.value.mode === 'resize-start') s = addDays(s, dd)
    else e = addDays(e, dd)
    if (e < s) { if (drag.value.mode === 'resize-start') s = e; else e = s }
  }
  const left = xFor(s)
  const width = Math.max((differenceInCalendarDays(e, s) + 1) * dayWidth.value, dayWidth.value)
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
    const ns = addDays(task.start, dd)
    patch[startField.value] = serialize(ns, d.raw.start, fieldType(startField.value))
  }
  if (d.mode === 'move' || d.mode === 'resize-end') {
    const ne = addDays(task.end, dd)
    patch[endField.value] = serialize(ne, d.raw.end, fieldType(endField.value))
  }

  // optimistic
  if (d.mode === 'move') { task.start = addDays(task.start, dd); task.end = addDays(task.end, dd) }
  else if (d.mode === 'resize-start') task.start = addDays(task.start, dd)
  else task.end = addDays(task.end, dd)
  if (task.end < task.start) task.end = task.start

  try {
    isSaving.value = true
    await docsApi.update(props.doctype.name, task.id, patch)
  } catch (e) {
    console.error('Gantt: reschedule failed', e)
    toast.error('Не вдалося оновити дати')
    await load()
  } finally {
    isSaving.value = false
  }
}

function rawOf(task: GanttTask, which: 'start' | 'end'): string {
  return which === 'start'
    ? format(task.start, "yyyy-MM-dd'T'00:00:00")
    : format(task.end, "yyyy-MM-dd'T'00:00:00")
}
function serialize(d: Date, original: unknown, ftype: string): string {
  const day = format(d, 'yyyy-MM-dd')
  if (ftype !== 'Datetime') return day
  const orig = String(original ?? '')
  const timePart = orig.includes('T') ? orig.split('T')[1] : orig.slice(11) || '00:00:00'
  return `${day}T${timePart || '00:00:00'}`
}

function openTask(task: GanttTask) {
  if (drag.value) return
  const base = props.workspace ? `/${props.workspace}` : ''
  router.push(`${base}/${props.doctype.name}/${task.id}`)
}

function fmtSpan(task: GanttTask) {
  return `${format(task.start, 'dd.MM.yy')} → ${format(task.end, 'dd.MM.yy')}`
}

const zoomOptions: { value: Zoom; label: string }[] = [
  { value: 'day', label: 'Дні' },
  { value: 'week', label: 'Тижні' },
  { value: 'month', label: 'Місяці' },
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
        <h2 class="text-base font-semibold text-foreground">Діаграма Ганта</h2>
        <span v-if="isSaving" class="text-xs text-primary animate-pulse">Оновлення…</span>
      </div>

      <div class="flex items-center gap-2">
        <div class="flex items-center rounded-md border border-border/50 bg-background p-0.5">
          <button v-for="opt in zoomOptions" :key="opt.value"
            class="px-2.5 h-7 text-xs font-medium rounded transition-colors"
            :class="zoom === opt.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'"
            @click="zoom = opt.value">{{ opt.label }}</button>
        </div>
        <div class="flex items-center rounded-md border border-border/50 bg-background p-0.5">
          <Button variant="ghost" size="sm" class="!h-7 !px-2" @click="nudge(-1)"><ChevronLeft class="size-4" /></Button>
          <Button variant="ghost" size="sm" class="!h-7 !px-3 !text-xs" @click="scrollToToday">Сьогодні</Button>
          <Button variant="ghost" size="sm" class="!h-7 !px-2" @click="nudge(1)"><ChevronRight class="size-4" /></Button>
        </div>
        <Spinner v-if="isLoading" class="!size-5" strokeWidth="6" />
      </div>
    </div>

    <!-- Not configured -->
    <div v-if="!isConfigured" class="flex-1 flex flex-col items-center justify-center gap-2 p-10 text-center text-muted-foreground">
      <ChartGantt class="size-8 opacity-40" />
      <p class="text-sm">Для діаграми Ганта потрібні поля початку та завершення (Date/Datetime).</p>
      <p class="text-xs">Оберіть їх у Конструкторі → вкладка «Вигляди» → «Діаграма Ганта».</p>
    </div>

    <!-- Chart -->
    <div v-else ref="scrollEl" class="flex-1 min-h-0 overflow-auto custom-scrollbar relative">
      <div class="flex" :style="{ width: `${chartWidth + 256}px` }">
        <!-- Frozen task column -->
        <div class="sticky left-0 z-30 shrink-0 w-64 border-r border-border/40 bg-card">
          <div class="sticky top-0 z-40 border-b border-border/40 bg-card px-3 flex items-end pb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider"
            :style="{ height: `${HEADER_H}px` }">
            {{ props.doctype.label }}
          </div>
          <div v-if="!isLoading && !tasks.length" class="p-4 text-xs text-muted-foreground">
            Немає документів із заповненими датами.
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
              class="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
              Немає документів із заповненими датами початку та завершення.
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
