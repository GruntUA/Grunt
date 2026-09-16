<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardWidget } from '@/types'

const props = defineProps<{
  widget: DashboardWidget
  data: { entries: { date: string; count: number }[] } | null
  loading?: boolean
}>()

const MONTHS_UK = ['Січ','Лют','Бер','Кві','Тра','Чер','Лип','Сер','Вер','Жов','Лис','Гру']

const PERIOD_DAYS: Record<string, number> = { '7d': 7, '30d': 30, '90d': 90, '365d': 365 }

const periodDays = computed(() => PERIOD_DAYS[props.widget.period ?? '365d'] ?? 365)

// Build week grid aligned to Monday for the widget's period
const grid = computed(() => {
  const entriesMap: Record<string, number> = {}
  for (const e of (props.data?.entries ?? [])) {
    entriesMap[e.date] = e.count
  }

  const today = new Date()
  const start = new Date(today)
  start.setDate(start.getDate() - (periodDays.value - 1))
  // Align to previous Monday
  const dow = (start.getDay() + 6) % 7
  start.setDate(start.getDate() - dow)

  // How many weeks do we need?
  const totalDays = Math.ceil((today.getTime() - start.getTime()) / 86400000) + 1
  const numWeeks = Math.ceil(totalDays / 7)

  const weeks: Array<Array<{ date: string; count: number; month: number }>> = []
  const monthLabels: Array<{ label: string; weekIdx: number }> = []

  let cur = new Date(start)
  let prevMonth = -1

  for (let w = 0; w < numWeeks; w++) {
    const week: Array<{ date: string; count: number; month: number }> = []
    for (let d = 0; d < 7; d++) {
      const dateStr = cur.toISOString().slice(0, 10)
      const mo = cur.getMonth()
      if (mo !== prevMonth && d === 0) {
        monthLabels.push({ label: MONTHS_UK[mo], weekIdx: w })
        prevMonth = mo
      }
      week.push({ date: dateStr, count: entriesMap[dateStr] ?? 0, month: mo })
      cur.setDate(cur.getDate() + 1)
    }
    weeks.push(week)
  }

  return { weeks, monthLabels, numWeeks }
})

const maxCount = computed(() => {
  let m = 0
  for (const e of (props.data?.entries ?? [])) if (e.count > m) m = e.count
  return m || 1
})

const totalCount = computed(() =>
  (props.data?.entries ?? []).reduce((s, e) => s + e.count, 0)
)

function cellColor(count: number): string {
  if (count === 0) return 'bg-muted/50'
  const ratio = count / maxCount.value
  if (ratio < 0.25) return 'bg-primary/25'
  if (ratio < 0.5)  return 'bg-primary/50'
  if (ratio < 0.75) return 'bg-primary/75'
  return 'bg-primary'
}
</script>

<template>
  <div class="flex flex-col h-full px-4 py-3">
    <!-- Header -->
    <div class="flex items-center justify-between mb-3 shrink-0">
      <p class="font-medium text-muted-foreground">{{ widget.title }}</p>
      <span v-if="!loading" class="text-muted-foreground">{{ totalCount }} за {{ periodDays }} дн.</span>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="grid gap-0.5 w-full" style="grid-template-columns: repeat(53, 1fr)">
        <div v-for="i in 53*7" :key="i" class="aspect-square rounded-sm bg-muted animate-pulse" />
      </div>
    </div>

    <template v-else>
      <!-- Month labels + Grid using CSS grid for full-width -->
      <div class="flex gap-1.5 flex-1 min-h-0">
        <!-- Day labels column -->
        <div class="flex flex-col justify-around shrink-0 pt-5 pb-0.5">
          <div v-for="d in ['Пн','','Ср','','Пт','','Нд']" :key="d"
            class="text-muted-foreground leading-none flex items-center h-0">
            {{ d }}
          </div>
        </div>

        <!-- Weeks grid -->
        <div class="flex-1 min-w-0 flex flex-col gap-0.5">
          <!-- Month labels row -->
          <div
            class="grid gap-0.5"
            :style="`grid-template-columns: repeat(${grid.numWeeks}, 1fr)`"
          >
            <div
              v-for="(_, wi) in grid.weeks" :key="wi"
              class="text-muted-foreground font-medium truncate leading-none h-4 flex items-end"
            >
              {{ grid.monthLabels.find(m => m.weekIdx === wi)?.label ?? '' }}
            </div>
          </div>

          <!-- Cells grid — rows=days, cols=weeks -->
          <div
            class="grid gap-0.5 flex-1"
            :style="`grid-template-columns: repeat(${grid.numWeeks}, 1fr); grid-template-rows: repeat(7, 1fr)`"
          >
            <template v-for="d in 7" :key="d">
              <div
                v-for="(week, wi) in grid.weeks"
                :key="`${wi}-${d}`"
                :title="`${week[d-1]?.date}: ${week[d-1]?.count}`"
                :class="['rounded-sm transition-colors', cellColor(week[d-1]?.count ?? 0)]"
                style="min-height: 8px"
              />
            </template>
          </div>
        </div>
      </div>

      <!-- Legend -->
      <div class="flex items-center gap-1 mt-2 shrink-0 justify-end">
        <span class="text-muted-foreground">Мало</span>
        <div v-for="lvl in [0, 0.25, 0.5, 0.75, 1]" :key="lvl"
          :class="['size-2.5 rounded-sm', lvl === 0 ? 'bg-muted/50' : lvl < 0.5 ? 'bg-primary/' + Math.round(lvl*100) : 'bg-primary']" />
        <span class="text-muted-foreground">Багато</span>
      </div>
    </template>
  </div>
</template>
