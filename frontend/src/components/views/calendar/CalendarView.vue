<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, shallowRef, computed, onMounted, watch } from 'vue'
import {
  endOfMonth,
  endOfWeek,
  getLocalTimeZone,
  isSameMonth,
  isToday,
  parseDateTime,
  startOfMonth,
  startOfWeek,
  toCalendarDate,
  today,
  type CalendarDate,
  type DateValue,
} from '@internationalized/date'
import type { DocType } from '@/types'
import { eachDate, formatCalendarDate, formatMonthYear, localeTag, toCalendarDay } from '@/core/datetime'
import { docsApi } from '@/core/api/docs'
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, Plus, ExternalLink } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { docUrl } from '@/core/workspaceUrl'

const { t } = useI18n()

const props = defineProps<{
  doctype: DocType
  dateField: string
  workspace?: string
  refreshKey?: number
}>()

const router = useRouter()
const currentMonth = shallowRef<CalendarDate>(today(getLocalTimeZone()))
const isLoading = ref(true)
const isRescheduling = ref(false)

const calendarDays = computed(() => {
  const start = startOfWeek(startOfMonth(currentMonth.value), localeTag(), 'mon')
  const end = endOfWeek(endOfMonth(currentMonth.value), localeTag(), 'mon')
  return eachDate(start, end)
})

const monthLabel = computed(() => {
  const label = formatMonthYear(currentMonth.value)
  return label.charAt(0).toUpperCase() + label.slice(1)
})

interface CalendarEvent {
  id: string
  name: string
  title: string
  date: string
  end_date?: string
  doctype: string
  color?: string
  recurring?: boolean
  event_type?: 'default' | 'birthday'
}

const events = ref<CalendarEvent[]>([])
const draggedEvent = ref<CalendarEvent | null>(null)
const dragOverDay = ref<string | null>(null)

// Popover for event details
const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)
const selectedEvent = ref<CalendarEvent | null>(null)

function normalizeBirthdayDate(rawDate: string, targetYear: number) {
  if (!rawDate) return null
  const birth = rawDate.slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(birth)) return null

  const monthDay = birth.slice(5)
  if (monthDay === '02-29') {
    const isLeapYear = (targetYear % 4 === 0 && targetYear % 100 !== 0) || targetYear % 400 === 0
    return `${targetYear}-${isLeapYear ? '02-29' : '02-28'}`
  }
  return `${targetYear}-${monthDay}`
}

function getBirthdayAge(rawDate: string, targetYear: number) {
  const year = Number(rawDate?.slice(0, 4))
  if (!Number.isFinite(year)) return null
  const age = targetYear - year
  return age >= 0 ? age : null
}

async function loadDocuments() {
  isLoading.value = true
  try {
    const endStr = endOfMonth(currentMonth.value).toString()
    const currentYear = currentMonth.value.year
    // The visible grid: whole weeks around the month, as 'yyyy-mm-dd' (compares as text).
    const gridStart = calendarDays.value[0].toString()
    const gridEnd = calendarDays.value[calendarDays.value.length - 1].toString()

    const endField = props.doctype.calendar_end_date_field
    const primaryFields = new Set(['name', props.dateField, props.doctype.title_field || 'name'])
    if (endField) primaryFields.add(endField)
    const primaryFetch = docsApi.list(props.doctype.name, {
      rawFilters: { [`${props.dateField}__lte`]: endStr },
      per_page: 200,
      fields: [...primaryFields].join(','),
    })

    const sources = props.doctype.calendar_sources || []
    const secondaryFetches = sources.map(source => {
      const sourceFields = new Set(['name', source.date_field, source.label_field || 'name'])
      if (source.end_date_field) sourceFields.add(source.end_date_field)
      return docsApi.list(source.ref_doctype, {
        rawFilters: {
          ...(source.filters || {}),
          ...(!source.recurring ? { [`${source.date_field}__lte`]: endStr } : {}),
        },
        per_page: 200,
        fields: [...sourceFields].join(','),
      })
    })

    const [primaryResp, ...secondaryResps] = await Promise.all([primaryFetch, ...secondaryFetches])
    const allEvents: CalendarEvent[] = []

    const overlaps = (start: string, end?: string, recurring?: boolean) => {
      if (!start) return false
      if (recurring) return true
      const s = start.slice(0, 10)
      const e = end ? end.slice(0, 10) : s
      return s <= gridEnd && e >= gridStart
    }

    if (primaryResp.data) {
      const primaryTitleField = props.doctype.title_field || 'name'
      primaryResp.data.forEach((doc: any) => {
        const d_start = doc[props.dateField]
        const d_end = endField ? doc[endField] : undefined
        if (overlaps(d_start, d_end)) {
          allEvents.push({
            id: doc.id,
            name: doc.name,
            title: String(doc[primaryTitleField] || doc.name || doc.id),
            date: d_start,
            end_date: d_end,
            doctype: props.doctype.name,
          })
        }
      })
    }

    secondaryResps.forEach((resp, idx) => {
      const source = sources[idx]
      if (resp.data) {
        resp.data.forEach((doc: any) => {
          const d_source = doc[source.date_field]
          const isBirthday = source.event_type === 'birthday'
          const d_start = isBirthday
            ? normalizeBirthdayDate(String(d_source || ''), currentYear)
            : d_source
          const d_end = source.end_date_field ? doc[source.end_date_field] : undefined
          const baseTitle = String(doc[source.label_field || 'name'] || doc.name || doc.id)
          const age = isBirthday && source.show_age ? getBirthdayAge(String(d_source || ''), currentYear) : null
          const title = isBirthday
            ? `🎂 ${baseTitle}${age !== null ? ` - ${age}` : ''}`
            : baseTitle

          if (overlaps(d_start, d_end, source.recurring)) {
            allEvents.push({
              id: doc.id,
              name: doc.name,
              title,
              date: d_start,
              end_date: d_end,
              doctype: source.ref_doctype,
              color: source.color,
              recurring: source.recurring,
              event_type: source.event_type || 'default',
            })
          }
        })
      }
    })

    events.value = allEvents
  } catch (error) {
    console.error('Failed to load events:', error)
  } finally {
    isLoading.value = false
  }
}

function getEventsForDay(day: CalendarDate) {
  const dStr = day.toString()
  const mDStr = dStr.slice(5)
  return events.value.filter(event => {
    if (!event.date) return false
    if (event.recurring) return event.date.includes(mDStr)
    const start = event.date.slice(0, 10)
    const end = event.end_date ? event.end_date.slice(0, 10) : start
    return dStr >= start && dStr <= end
  })
}

// Cap the chips rendered inside a day cell; the rest collapse into a "+N ще"
// popover so a busy day never overflows the grid.
const MAX_VISIBLE_EVENTS = 3
function hiddenEventCount(day: CalendarDate) {
  return Math.max(0, getEventsForDay(day).length - MAX_VISIBLE_EVENTS)
}
function dayFullLabel(day: CalendarDate) {
  return formatCalendarDate(day, { day: 'numeric', month: 'long' })
}

function nextMonth() { currentMonth.value = currentMonth.value.add({ months: 1 }) }
function prevMonth() { currentMonth.value = currentMonth.value.subtract({ months: 1 }) }
function setToday() { currentMonth.value = today(getLocalTimeZone()) }

// Month picker (replaces the native <input type="month">)
const isPickerOpen = ref(false)
const pickerValue = computed<DateValue | null>({
  get() {
    return currentMonth.value
  },
  set(val) {
    if (!val) return
    currentMonth.value = startOfMonth(toCalendarDate(val))
    isPickerOpen.value = false
  },
})

function fmtDate(d: string | null) {
  const opts: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'long', year: 'numeric' }
  // A Datetime value shows its wall-clock time as stored; a bare Date shows no time.
  if (d && /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(d)) {
    return formatCalendarDate(parseDateTime(d.slice(0, 19).replace(' ', 'T')), {
      ...opts, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    })
  }
  const day = toCalendarDay(d)
  return day ? formatCalendarDate(day, opts) : ''
}

onMounted(loadDocuments)
watch(currentMonth, loadDocuments)
// Bumped by the shared header's Refresh button (calendar events aren't on the shared query cache).
watch(() => props.refreshKey, (_v, old) => { if (old !== undefined) loadDocuments() })

function navigateToDoc(event: CalendarEvent) {
  const id = String(event.id)
  router.push(docUrl(event.doctype, id, props.workspace))
}

function showEventDetails(event: CalendarEvent, target: EventTarget | null) {
    selectedEvent.value = event
    anchorEl.value = target as HTMLElement | null
    isOpen.value = !isOpen.value
}

// DRAG AND DROP
function onDragStart(e: DragEvent, event: CalendarEvent) {
  if (event.recurring) {
    e.preventDefault()
    return
  }
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('application/json', JSON.stringify(event))
  }
  draggedEvent.value = event
}

function onDragEnd() {
  draggedEvent.value = null
  dragOverDay.value = null
}

function onDragOver(day: CalendarDate) {
  dragOverDay.value = day.toString()
}

async function onDrop(e: DragEvent, day: CalendarDate) {
  dragOverDay.value = null
  const data = e.dataTransfer?.getData('application/json')
  if (!data) return

  const event = JSON.parse(data) as CalendarEvent
  if (event.recurring) return
  const dateField = event.doctype === props.doctype.name
    ? props.dateField
    : props.doctype.calendar_sources?.find(s => s.ref_doctype === event.doctype)?.date_field

  if (!dateField) return

  const newDate = day.toString() + (event.date.includes('T') ? 'T' + event.date.split('T')[1] : ' 00:00:00')
  const oldDate = event.date
  event.date = newDate // Optimistic

  try {
    isRescheduling.value = true
    await docsApi.update(event.doctype, event.id, { [dateField]: newDate })
    await loadDocuments()
  } catch (err) {
    event.date = oldDate
    console.error('Failed to reschedule:', err)
  } finally {
    isRescheduling.value = false
  }
}

function onDayClick(day: CalendarDate) {
  const path = docUrl(props.doctype.name, 'new', props.workspace)

  router.push({
    path,
    state: {
      initial_data: JSON.stringify({ [props.dateField]: day.toString() })
    }
  })
}

const weekDays = [t('Mon'), t('Tue'), t('Wed'), t('Thu'), t('Fri'), t('Sat'), t('Sun')]
</script>

<template>
  <div class="flex flex-col h-full bg-card border border-border/60 rounded-lg overflow-hidden">
    <!-- Toolbar -->
    <div class="flex items-center justify-between gap-3 p-3 border-b border-border/40 bg-muted/20">
      <div class="flex items-center gap-2">
        <div class="size-8 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
          <CalendarIcon class="size-4 text-primary" />
        </div>

        <Popover v-model:open="isPickerOpen">
          <PopoverTrigger as-child>
            <Button variant="ghost" size="sm" class="!h-8 !px-2 text-base font-semibold">
              {{ monthLabel }}
            </Button>
          </PopoverTrigger>
          <PopoverContent class="w-auto p-0" align="start">
            <Calendar v-model="pickerValue" />
          </PopoverContent>
        </Popover>

        <span v-if="isRescheduling" class="text-primary animate-pulse">{{ t('Updating…') }}</span>
      </div>

      <div class="flex items-center gap-2">
        <div class="flex items-center rounded-md border border-border/50 bg-background p-0.5">
          <Button variant="ghost" size="sm" class="!h-7 !px-2" @click="prevMonth"><ChevronLeft class="size-4" /></Button>
          <Button variant="ghost" size="sm" class="!h-7 !px-3" @click="setToday">{{ t('Today') }}</Button>
          <Button variant="ghost" size="sm" class="!h-7 !px-2" @click="nextMonth"><ChevronRight class="size-4" /></Button>
        </div>
        <Spinner v-if="isLoading" class="!size-5" strokeWidth="6" />
      </div>
    </div>

    <!-- Calendar Grid -->
    <div class="flex-1 flex flex-col overflow-hidden relative">
      <!-- Weekday headers -->
      <div class="grid grid-cols-7 border-b border-border/40">
        <div v-for="day in weekDays" :key="day"
          class="py-2 text-center font-medium text-muted-foreground">
          {{ day }}
        </div>
      </div>

      <!-- Days grid -->
      <div class="flex-1 grid grid-cols-7 auto-rows-fr overflow-y-auto custom-scrollbar bg-border/60 gap-px">
        <div v-for="day in calendarDays" :key="day.toString()"
          class="min-h-32 bg-card p-1.5 flex flex-col gap-1 relative group cursor-default transition-colors"
          :class="{
            'bg-muted/30 text-muted-foreground': !isSameMonth(day, currentMonth),
            'ring-2 ring-inset ring-primary/60 bg-primary/5 z-10': dragOverDay === day.toString()
          }" @dragover.prevent="onDragOver(day)" @drop="onDrop($event, day)" @click.self="onDayClick(day)">

          <!-- Day header -->
          <div class="flex justify-between items-center">
            <span class="font-medium size-6 flex items-center justify-center rounded-md" :class="[
              isToday(day, getLocalTimeZone())
                ? 'bg-primary text-primary-foreground'
                : isSameMonth(day, currentMonth) ? 'text-foreground' : 'text-muted-foreground/50'
            ]">
              {{ day.day }}
            </span>

            <Button variant="ghost" size="icon" class="size-6 opacity-0 group-hover:opacity-100 text-muted-foreground" @click.stop="onDayClick(day)"><Plus class="size-4" /></Button>
          </div>

          <!-- Event chips -->
          <div class="flex flex-col gap-1 min-h-0">
            <div v-for="event in getEventsForDay(day).slice(0, MAX_VISIBLE_EVENTS)" :key="event.doctype + event.id" draggable="true"
              class="group/event flex items-center gap-1.5 rounded px-1.5 py-1 leading-tight truncate cursor-pointer transition-colors"
              :class="[
                event.doctype === doctype.name
                  ? 'bg-muted hover:bg-accent text-foreground'
                  : 'text-muted-foreground hover:bg-accent'
              ]"
              @click="navigateToDoc(event)"
              @dragstart="onDragStart($event, event)"
              @dragend="onDragEnd"
              @contextmenu.prevent="showEventDetails(event, $event.target)"
            >
              <span class="size-1.5 rounded-full shrink-0" :style="{ background: event.color || 'var(--primary)' }" />
              <span class="truncate">{{ event.title }}</span>
            </div>

            <Popover v-if="hiddenEventCount(day) > 0">
              <PopoverTrigger as-child>
                <button
                  class="rounded px-1.5 py-0.5 text-left font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  @click.stop
                >
                  +{{ hiddenEventCount(day) }} {{ t('more') }}
                </button>
              </PopoverTrigger>
              <PopoverContent class="w-60 p-1" align="start">
                <div class="flex items-center justify-between px-2 py-1.5">
                  <span class="font-semibold">{{ dayFullLabel(day) }}</span>
                  <span class="text-muted-foreground">{{ getEventsForDay(day).length }}</span>
                </div>
                <Separator class="my-1" />
                <div class="-mx-1 max-h-64 overflow-y-auto custom-scrollbar px-1">
                  <button
                    v-for="event in getEventsForDay(day)"
                    :key="event.doctype + event.id"
                    class="flex w-full cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-left outline-hidden transition-colors hover:bg-accent hover:text-accent-foreground"
                    @click="navigateToDoc(event)"
                  >
                    <span class="size-1.5 shrink-0 rounded-full" :style="{ background: event.color || 'var(--primary)' }" />
                    <span class="truncate">{{ event.title }}</span>
                  </button>
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </div>
      </div>
    </div>

    <!-- Event Detail Popover -->
    <Popover v-model:open="isOpen">
      <PopoverAnchor :reference="anchorEl ?? undefined" />
      <PopoverContent class="w-64 p-3">
        <div v-if="selectedEvent" class="flex flex-col gap-3">
          <div class="flex items-start justify-between gap-2">
            <div class="flex flex-col min-w-0">
              <span class="text-muted-foreground truncate">{{ selectedEvent.doctype }}</span>
              <h3 class="font-semibold text-foreground leading-tight">{{ selectedEvent.title }}</h3>
            </div>
            <Button variant="ghost" size="icon" class="size-7 shrink-0" @click="navigateToDoc(selectedEvent)"><ExternalLink class="size-4" /></Button>
          </div>

          <div class="flex items-center gap-2 text-muted-foreground border-t border-border/40 pt-2">
            <CalendarIcon class="size-3.5" />
            <span>{{ fmtDate(selectedEvent.date) }}</span>
          </div>

          <Button size="sm" class="w-full" @click="navigateToDoc(selectedEvent)">{{ t('Open') }}</Button>
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 10px;
  border: 1px solid transparent;
  background-clip: padding-box;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: var(--primary);
}
</style>
