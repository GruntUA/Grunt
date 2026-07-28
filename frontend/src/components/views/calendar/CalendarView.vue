<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  format,
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  isSameMonth,
  addMonths,
  subMonths,
  parseISO,
  isToday,
  parse
} from 'date-fns'
import { uk } from 'date-fns/locale'
import type { DocType } from '@/types'
import { docsApi } from '@/core/api/docs'
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, Plus, ExternalLink } from '@lucide/vue'
import { useRouter } from 'vue-router'

const props = defineProps<{
  doctype: DocType
  dateField: string
  workspace?: string
}>()

const router = useRouter()
const currentMonth = ref(new Date())
const isLoading = ref(true)
const isRescheduling = ref(false)

const calendarDays = computed(() => {
  const start = startOfWeek(startOfMonth(currentMonth.value), { weekStartsOn: 1 })
  const end = endOfWeek(endOfMonth(currentMonth.value), { weekStartsOn: 1 })
  return eachDayOfInterval({ start, end })
})

const monthLabel = computed(() => {
  const label = format(currentMonth.value, 'LLLL yyyy', { locale: uk })
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
    const startM = startOfMonth(currentMonth.value)
    const endM = endOfMonth(currentMonth.value)
    const endStr = format(endM, 'yyyy-MM-dd')
    const currentYear = currentMonth.value.getFullYear()

    const endField = props.doctype.calendar_view?.end_field
    const primaryFetch = docsApi.list(props.doctype.name, {
      rawFilters: { [`${props.dateField}__lte`]: endStr },
      per_page: 200,
    })

    const sources = props.doctype.calendar_view?.sources || []
    const secondaryFetches = sources.map(source =>
      docsApi.list(source.doctype, {
        rawFilters: {
          ...(source.filters || {}),
          ...(!source.recurring ? { [`${source.date_field}__lte`]: endStr } : {}),
        },
        per_page: 200,
      })
    )

    const [primaryResp, ...secondaryResps] = await Promise.all([primaryFetch, ...secondaryFetches])
    const allEvents: CalendarEvent[] = []

    const overlaps = (start: string, end?: string, recurring?: boolean) => {
      if (!start) return false
      if (recurring) return true
      const s = parseISO(start.slice(0, 10))
      const e = end ? parseISO(end.slice(0, 10)) : s
      const mS = startOfWeek(startM, { weekStartsOn: 1 })
      const mE = endOfWeek(endM, { weekStartsOn: 1 })
      return s <= mE && e >= mS
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
              doctype: source.doctype,
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

function getEventsForDay(day: Date) {
  const dStr = format(day, 'yyyy-MM-dd')
  const mDStr = format(day, 'MM-dd')
  return events.value.filter(event => {
    if (!event.date) return false
    if (event.recurring) return event.date.includes(mDStr)
    const start = event.date.slice(0, 10)
    const end = event.end_date ? event.end_date.slice(0, 10) : start
    return dStr >= start && dStr <= end
  })
}

function nextMonth() { currentMonth.value = addMonths(currentMonth.value, 1) }
function prevMonth() { currentMonth.value = subMonths(currentMonth.value, 1) }
function setToday() { currentMonth.value = new Date() }

function fmtDate(d: string | null) {
  if (!d) return ''
  return format(parseISO(d.slice(0, 19)), 'dd MMMM yyyy, HH:mm', { locale: uk })
}

onMounted(loadDocuments)
watch(currentMonth, loadDocuments)

function navigateToDoc(event: CalendarEvent) {
  const id = String(event.id)
  router.push(props.workspace ? `/${props.workspace}/${event.doctype}/${id}` : `/${event.doctype}/${id}`)
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

function onDragOver(day: Date) {
  dragOverDay.value = day.toISOString()
}

async function onDrop(e: DragEvent, day: Date) {
  dragOverDay.value = null
  const data = e.dataTransfer?.getData('application/json')
  if (!data) return

  const event = JSON.parse(data) as CalendarEvent
  if (event.recurring) return
  const dateField = event.doctype === props.doctype.name
    ? props.dateField
    : props.doctype.calendar_view?.sources?.find(s => s.doctype === event.doctype)?.date_field

  if (!dateField) return

  const newDate = format(day, 'yyyy-MM-dd') + (event.date.includes('T') ? 'T' + event.date.split('T')[1] : ' 00:00:00')
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

function onDayClick(day: Date) {
  const path = props.workspace
    ? `/${props.workspace}/${props.doctype.name}/new`
    : `/${props.doctype.name}/new`

  router.push({
    path,
    state: {
      initial_data: JSON.stringify({ [props.dateField]: format(day, 'yyyy-MM-dd') })
    }
  })
}

const weekDays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']
</script>

<template>
  <div class="flex flex-col h-full bg-card border border-border/60 rounded-xl overflow-hidden shadow-lg transition-all duration-500">
    <!-- Toolbar -->
    <div class="flex items-center justify-between p-4 border-b border-border/40 bg-muted/20">
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2">
            <div class="size-9 rounded-lg bg-primary/10 flex items-center justify-center border border-primary/20">
                <CalendarIcon class="size-5 text-primary" />
            </div>
            <h2 class="text-xl font-bold text-foreground tracking-tight">{{ monthLabel }}</h2>
        </div>
        
        <div class="flex items-center p-1 bg-background rounded-xl border border-border/40 shadow-sm">
            <Button variant="ghost" size="sm" class="!px-3 !h-8" @click="prevMonth">
                <ChevronLeft class="size-4" />
            </Button>
            <Button variant="ghost" size="sm" class="!px-4 !h-8 !text-xs font-bold uppercase tracking-wider !text-muted-foreground hover:!text-primary" @click="setToday">
                Сьогодні
            </Button>
            <Button variant="ghost" size="sm" class="!px-3 !h-8" @click="nextMonth">
                <ChevronRight class="size-4" />
            </Button>
        </div>
      </div>

      <div class="flex items-center gap-4">
        <!-- Month Picker -->
        <input
          type="month"
          :value="format(currentMonth, 'yyyy-MM')"
          class="!w-48 !h-10 rounded-md border border-input bg-transparent px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
          @change="currentMonth = parse(($event.target as HTMLInputElement).value, 'yyyy-MM', new Date())"
        >
        
        <div class="flex items-center gap-2">
            <div v-if="isRescheduling" class="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-primary animate-pulse bg-primary/10 px-2 py-1 rounded-full">
                Оновлення...
            </div>
            <Spinner v-if="isLoading" class="!size-6" strokeWidth="6" />
        </div>
      </div>
    </div>

    <!-- Calendar Grid -->
    <div class="flex-1 flex flex-col overflow-hidden relative">
      <!-- Weekday headers -->
      <div class="grid grid-cols-7 border-b border-border/40 bg-muted/5">
        <div v-for="day in weekDays" :key="day"
          class="py-3 text-center text-[10px] font-black text-muted-foreground/60 uppercase tracking-[0.2em]">
          {{ day }}
        </div>
      </div>

      <!-- Days grid -->
      <div class="flex-1 grid grid-cols-7 auto-rows-fr overflow-y-auto custom-scrollbar bg-border/10 gap-px">
        <div v-for="day in calendarDays" :key="day.toISOString()"
          class="min-h-36 bg-card p-2 transition-all flex flex-col gap-1.5 relative group cursor-default"
          :class="{
            'bg-muted/10 opacity-60': !isSameMonth(day, currentMonth),
            'ring-2 ring-inset ring-primary/60 bg-primary/5 z-10': dragOverDay === day.toISOString()
          }" @dragover.prevent="onDragOver(day)" @drop="onDrop($event, day)" @click.self="onDayClick(day)">
          
          <!-- Day header -->
          <div class="flex justify-between items-center mb-1">
            <span class="text-xs font-black size-8 flex items-center justify-center rounded-xl transition-all" :class="[
              isToday(day)
                ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/20 scale-110'
                : isSameMonth(day, currentMonth) ? 'text-foreground/80 hover:bg-muted/50' : 'text-muted-foreground/20'
            ]">
              {{ format(day, 'd') }}
            </span>

            <Button variant="ghost" size="sm" class="!size-7 opacity-0 group-hover:opacity-100 transition-all !text-muted-foreground/40 hover:!text-primary hover:!bg-primary/5 rounded-full" @click.stop="onDayClick(day)"><Plus class="size-4" /></Button>
          </div>

          <!-- Event cards -->
          <div class="flex flex-col gap-1.5 overflow-y-auto max-h-48 scrollbar-hide py-0.5">
            <div v-for="event in getEventsForDay(day)" :key="event.doctype + event.id" draggable="true"
              class="group/event relative text-[11px] font-bold leading-tight pl-2.5 pr-2 py-2 rounded-xl border shadow-sm truncate cursor-pointer transition-all hover:translate-y-[-1px] hover:shadow-md active:scale-95 active:opacity-70"
              :class="[
                event.doctype === doctype.name
                  ? 'bg-background border-border hover:border-primary/40 text-foreground'
                  : 'bg-muted/30 border-border/40 text-muted-foreground hover:bg-muted/50'
              ]"
              :style="event.color ? { borderLeft: `3px solid ${event.color}` } : { borderLeft: `3px solid var(--primary)` }"
              @click="navigateToDoc(event)" 
              @dragstart="onDragStart($event, event)" 
              @dragend="onDragEnd"
              @contextmenu.prevent="showEventDetails(event, $event.target)"
            >
              <div class="flex items-center gap-1.5">
                  <div v-if="event.doctype !== doctype.name" class="size-1.5 rounded-full bg-primary/40 shrink-0" />
                  <span class="truncate">{{ event.title }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Event Detail Popover -->
    <Popover v-model:open="isOpen">
      <PopoverAnchor :reference="anchorEl ?? undefined" />
      <PopoverContent class="w-auto p-0">
        <div v-if="selectedEvent" class="w-64 p-3 flex flex-col gap-3">
            <div class="flex items-start justify-between">
                <div class="flex flex-col">
                    <span class="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{{ selectedEvent.doctype }}</span>
                    <h3 class="text-sm font-black text-foreground leading-tight">{{ selectedEvent.title }}</h3>
                </div>
                <Button variant="ghost" size="sm" @click="navigateToDoc(selectedEvent)" class="rounded-full"><ExternalLink class="size-4" /></Button>
            </div>
            
            <div class="flex flex-col gap-1.5 py-2 border-t border-border/40">
                <div class="flex items-center gap-2 text-xs text-muted-foreground">
                    <CalendarIcon class="size-3.5" />
                    <span>{{ fmtDate(selectedEvent.date) }}</span>
                </div>
            </div>

            <Button size="sm" class="w-full" @click="navigateToDoc(selectedEvent)">Відкрити</Button>
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>

<style scoped>
.scrollbar-hide::-webkit-scrollbar { display: none; }
.scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }

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
