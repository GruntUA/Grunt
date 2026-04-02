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
  isToday
} from 'date-fns'
import { uk } from 'date-fns/locale'
import type { DocType } from '@/types'
import { docsApi } from '@/core/api/docs'
import { Spinner } from '@/components/ui/spinner'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-vue-next'
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
}

const events = ref<CalendarEvent[]>([])
const draggedEvent = ref<CalendarEvent | null>(null)
const dragOverDay = ref<string | null>(null)

async function loadDocuments() {
  isLoading.value = true
  try {
    const startM = startOfMonth(currentMonth.value)
    const endM = endOfMonth(currentMonth.value)
    const endStr = format(endM, 'yyyy-MM-dd')

    // 1. Primary source
    const endField = props.doctype.calendar_view?.end_field
    const primaryFetch = docsApi.list(props.doctype.name, {
      filters: {
        [`${props.dateField}__lte`]: endStr,
      },
      per_page: 200,
    })

    // 2. Secondary sources
    const sources = props.doctype.calendar_view?.sources || []
    const secondaryFetches = sources.map(source =>
      docsApi.list(source.doctype, {
        filters: {
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
      if (recurring) return true // Show recurring events like birthdays every year
      const s = parseISO(start.slice(0, 10))
      const e = end ? parseISO(end.slice(0, 10)) : s
      // Simple range check for month view (+/- week for edges)
      const mS = startOfWeek(startM, { weekStartsOn: 1 })
      const mE = endOfWeek(endM, { weekStartsOn: 1 })
      return s <= mE && e >= mS
    }

    // Add primary events
    const primaryTitleField = props.doctype.title_field || 'name'
    if (primaryResp.data) {
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

    // Add secondary events
    secondaryResps.forEach((resp, idx) => {
      const source = sources[idx]
      if (resp.data) {
        resp.data.forEach((doc: any) => {
          const d_start = doc[source.date_field]
          const d_end = source.end_date_field ? doc[source.end_date_field] : undefined
          if (overlaps(d_start, d_end, source.recurring)) {
            allEvents.push({
              id: doc.id,
              name: doc.name,
              title: source.recurring ? `🎂 ${String(doc[source.label_field || 'name'] || doc.name)}` : String(doc[source.label_field || 'name'] || doc.name || doc.id),
              date: d_start,
              end_date: d_end,
              doctype: source.doctype,
              color: source.color,
              recurring: source.recurring
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
    if (event.recurring) {
      return event.date.includes(mDStr)
    }
    const start = event.date.slice(0, 10)
    const end = event.end_date ? event.end_date.slice(0, 10) : start
    return dStr >= start && dStr <= end
  })
}

function nextMonth() { currentMonth.value = addMonths(currentMonth.value, 1) }
function prevMonth() { currentMonth.value = subMonths(currentMonth.value, 1) }
function setToday() { currentMonth.value = new Date() }

onMounted(loadDocuments)
watch(currentMonth, loadDocuments)

function navigateToDoc(event: CalendarEvent) {
  const id = String(event.id)
  router.push(props.workspace ? `/${props.workspace}/list/${event.doctype}/${id}` : `/${event.doctype}/${id}`)
}

// DRAG AND DROP
function onDragStart(e: DragEvent, event: CalendarEvent) {
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
  const dateField = event.doctype === props.doctype.name
    ? props.dateField
    : props.doctype.calendar_view?.sources?.find(s => s.doctype === event.doctype)?.date_field

  if (!dateField) return

  const newDate = format(day, 'yyyy-MM-dd') + (event.date.includes('T') ? 'T' + event.date.split('T')[1] : ' 00:00:00')

  // Optimistic UI
  const oldDate = event.date
  event.date = newDate

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
    ? `/${props.workspace}/list/${props.doctype.name}/new`
    : `/${props.doctype.name}/new`

  router.push({
    path,
    state: {
      initial_data: JSON.stringify({
        [props.dateField]: format(day, 'yyyy-MM-dd')
      })
    }
  })
}

const weekDays = ['Пн', 'Вв', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']
</script>

<template>
  <div
    class="flex flex-col h-full bg-card border border-border rounded-xl overflow-hidden shadow-sm transition-all duration-300">
    <!-- Toolbar -->
    <div class="flex items-center justify-between p-4 border-b border-border bg-muted/30">
      <div class="flex items-center gap-4">
        <h2 class="text-lg font-bold text-foreground min-w-48 tracking-tight">{{ monthLabel }}</h2>
        <div class="flex items-center rounded-lg border border-border bg-background shadow-sm overflow-hidden">
          <button class="p-2 hover:bg-muted transition-colors border-r border-border" @click="prevMonth">
            <ChevronLeft class="size-4" />
          </button>
          <button class="px-4 py-1.5 text-xs font-semibold hover:bg-muted transition-colors" @click="setToday">
            Сьогодні
          </button>
          <button class="p-2 hover:bg-muted transition-colors border-l border-border" @click="nextMonth">
            <ChevronRight class="size-4" />
          </button>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <div v-if="isRescheduling" class="flex items-center gap-2 text-xs text-muted-foreground animate-pulse">
          Оновлення...
        </div>
        <div v-if="isLoading" class="flex items-center">
          <Spinner size="sm" />
        </div>
      </div>
    </div>

    <!-- Calendar Grid -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- Weekday headers -->
      <div class="grid grid-cols-7 border-b border-border bg-muted/10">
        <div v-for="day in weekDays" :key="day"
          class="py-2.5 text-center text-[11px] font-bold text-muted-foreground uppercase tracking-widest">
          {{ day }}
        </div>
      </div>

      <!-- Days grid -->
      <div class="flex-1 grid grid-cols-7 auto-rows-fr overflow-y-auto custom-scrollbar">
        <div v-for="day in calendarDays" :key="day.toISOString()"
          class="min-h-32 border-r border-b border-border p-1.5 transition-all flex flex-col gap-1 relative group"
          :class="{
            'bg-muted/5 opacity-60': !isSameMonth(day, currentMonth),
            'bg-card': isSameMonth(day, currentMonth),
            'ring-2 ring-inset ring-primary/40 bg-primary/5 z-10': dragOverDay === day.toISOString()
          }" @dragover.prevent="onDragOver(day)" @drop="onDrop($event, day)" @click.self="onDayClick(day)">
          <!-- Day number -->
          <div class="flex justify-between items-start mb-0.5 px-0.5">
            <span class="text-xs font-bold size-7 flex items-center justify-center rounded-lg transition-all" :class="[
              isToday(day)
                ? 'bg-primary text-primary-foreground shadow-sm scale-110'
                : isSameMonth(day, currentMonth) ? 'text-foreground/80' : 'text-muted-foreground/30'
            ]">
              {{ format(day, 'd') }}
            </span>

            <!-- Quick add hidden button -->
            <button
              class="opacity-0 group-hover:opacity-100 p-1 rounded-md hover:bg-muted text-muted-foreground/60 hover:text-primary transition-all"
              @click.stop="onDayClick(day)">
              <Plus class="size-3.5" />
            </button>
          </div>

          <!-- Event cards -->
          <div class="flex flex-col gap-1 overflow-y-auto max-h-40 scrollbar-hide py-0.5">
            <div v-for="event in getEventsForDay(day)" :key="event.doctype + event.id" draggable="true"
              class="text-[11px] leading-snug px-2 py-1.5 rounded-lg border shadow-sm truncate cursor-pointer transition-all hover:scale-[1.02] active:scale-95 active:opacity-70"
              :class="[
                event.doctype === doctype.name
                  ? 'bg-primary/5 border-primary/20 text-primary font-medium hover:bg-primary/10'
                  : 'bg-muted/50 border-border/50 text-muted-foreground hover:bg-muted'
              ]"
              :style="event.color ? { backgroundColor: `${event.color}15`, borderColor: `${event.color}30`, color: event.color } : {}"
              @click="navigateToDoc(event)" @dragstart="onDragStart($event, event)" @dragend="onDragEnd">
              <span v-if="event.doctype !== doctype.name" class="opacity-60 font-bold mr-1">[{{ event.doctype }}]</span>
              {{ event.title }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}

.scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 10px;
}
</style>

<style scoped>
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}

.scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
