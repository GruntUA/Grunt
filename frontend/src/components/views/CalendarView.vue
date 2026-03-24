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
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

const props = defineProps<{
  doctype: DocType
  dateField: string
  workspace?: string
}>()

const router = useRouter()
const currentMonth = ref(new Date())
const isLoading = ref(true)

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
}

const events = ref<CalendarEvent[]>([])

async function loadDocuments() {
  isLoading.value = true
  try {
    const startMonth = startOfMonth(currentMonth.value)
    const endMonth = endOfMonth(currentMonth.value)
    const endStr = format(endMonth, 'yyyy-MM-dd')
    
    // 1. Primary source
    const endField = props.doctype.calendar_view?.end_field
    const primaryFetch = docsApi.list(props.doctype.name, {
      filters: {
        [`${props.dateField}__lte`]: endStr, // Starts before month end
      },
      per_page: 500,
    })

    // 2. Secondary sources
    const sources = props.doctype.calendar_view?.sources || []
    const secondaryFetches = sources.map(source => 
      docsApi.list(source.doctype, {
        filters: {
          ...(source.filters || {}),
          [`${source.date_field}__lte`]: endStr,
        },
        per_page: 200,
      })
    )

    const [primaryResp, ...secondaryResps] = await Promise.all([primaryFetch, ...secondaryFetches])
    
    const allEvents: CalendarEvent[] = []
    
    // helper to filter by range overlap on frontend
    const overlaps = (start: string, end?: string) => {
      if (!start) return false
      const s = parseISO(start.slice(0, 10))
      const e = end ? parseISO(end.slice(0, 10)) : s
      return s <= endMonth && e >= startMonth
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
          if (overlaps(d_start, d_end)) {
            allEvents.push({
              id: doc.id,
              name: doc.name,
              title: String(doc[source.label_field || 'name'] || doc.name || doc.id),
              date: d_start,
              end_date: d_end,
              doctype: source.doctype,
              color: source.color
            })
          }
        })
      }
    })

    events.value = allEvents
  } catch (error) {
    console.error('Failed to load events for calendar:', error)
  } finally {
    isLoading.value = false
  }
}

function getEventsForDay(day: Date) {
  return events.value.filter(event => {
    if (!event.date) return false
    const start = parseISO(event.date.slice(0, 10))
    const end = event.end_date ? parseISO(event.end_date.slice(0, 10)) : start
    return day >= start && day <= end
  })
}

function nextMonth() {
  currentMonth.value = addMonths(currentMonth.value, 1)
}

function prevMonth() {
  currentMonth.value = subMonths(currentMonth.value, 1)
}

function setToday() {
  currentMonth.value = new Date()
}

onMounted(loadDocuments)
watch(currentMonth, loadDocuments)

function navigateToDoc(event: CalendarEvent) {
  const id = String(event.id)
  router.push(props.workspace ? `/${props.workspace}/list/${event.doctype}/${id}` : `/${event.doctype}/${id}`)
}

const weekDays = ['Пн', 'Вв', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']
</script>

<template>
  <div class="flex flex-col h-full bg-card border border-border rounded-xl overflow-hidden shadow-sm">
    <!-- Toolbar -->
    <div class="flex items-center justify-between p-4 border-b border-border bg-muted/30">
      <div class="flex items-center gap-4">
        <h2 class="text-lg font-semibold text-foreground min-w-40">{{ monthLabel }}</h2>
        <div class="flex items-center rounded-md border border-border bg-card overflow-hidden">
          <Button variant="ghost" size="icon-sm" class="rounded-none border-r border-border" @click="prevMonth">
            <ChevronLeft class="size-4" />
          </Button>
          <Button variant="ghost" size="sm" class="rounded-none text-xs font-medium px-3" @click="setToday">
            Сьогодні
          </Button>
          <Button variant="ghost" size="icon-sm" class="rounded-none border-l border-border" @click="nextMonth">
            <ChevronRight class="size-4" />
          </Button>
        </div>
      </div>
      
      <div v-if="isLoading" class="flex items-center">
        <Spinner size="sm" />
      </div>
    </div>

    <!-- Calendar Grid -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- Weekday headers -->
      <div class="grid grid-cols-7 border-b border-border bg-muted/20">
        <div 
          v-for="day in weekDays" 
          :key="day" 
          class="py-2 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wider"
        >
          {{ day }}
        </div>
      </div>

      <!-- Days grid -->
      <div class="flex-1 grid grid-cols-7 auto-rows-fr overflow-y-auto">
        <div 
          v-for="day in calendarDays" 
          :key="day.toISOString()"
          class="min-h-32 border-r border-b border-border p-2 transition-colors flex flex-col gap-1"
          :class="{
            'bg-muted/10': !isSameMonth(day, currentMonth),
            'bg-card': isSameMonth(day, currentMonth),
          }"
        >
          <!-- Day number -->
          <div class="flex justify-between items-start mb-1">
            <span 
              class="text-xs font-medium size-6 flex items-center justify-center rounded-full"
              :class="[
                isToday(day) 
                  ? 'bg-primary text-primary-foreground' 
                  : isSameMonth(day, currentMonth) ? 'text-foreground' : 'text-muted-foreground/40'
              ]"
            >
              {{ format(day, 'd') }}
            </span>
          </div>

          <!-- Event cards -->
          <div class="flex flex-col gap-1 overflow-y-auto max-h-40 scrollbar-hide">
            <div 
              v-for="event in getEventsForDay(day)" 
              :key="event.doctype + event.id"
              class="text-[11px] leading-tight px-1.5 py-1 rounded border truncate cursor-pointer transition-colors"
              :class="[
                event.doctype === doctype.name 
                  ? 'bg-primary/10 border-primary/20 text-primary hover:bg-primary/20' 
                  : 'bg-muted border-border text-muted-foreground hover:bg-muted-foreground/10'
              ]"
              :style="event.color ? { backgroundColor: `${event.color}20`, borderColor: `${event.color}40`, color: event.color } : {}"
              @click="navigateToDoc(event)"
            >
              <span v-if="event.doctype !== doctype.name" class="opacity-70 mr-1">[{{ event.doctype }}]</span>
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
</style>
