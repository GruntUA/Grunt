<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardWidget } from '@/types'

const props = defineProps<{
  widget: DashboardWidget
  data: { entries: { date: string; count: number }[] } | null
  loading?: boolean
}>()

const MONTHS_UK = ['Січ','Лют','Бер','Кві','Тра','Чер','Лип','Сер','Вер','Жов','Лис','Гру']

// Build 52-week grid (Mon..Sun columns), similar to GitHub
const grid = computed(() => {
  const entriesMap: Record<string, number> = {}
  for (const e of (props.data?.entries ?? [])) {
    entriesMap[e.date] = e.count
  }

  const today = new Date()
  // Start from 364 days ago, aligned to Monday
  const start = new Date(today)
  start.setDate(start.getDate() - 363)
  // Move to previous Monday
  const dow = (start.getDay() + 6) % 7
  start.setDate(start.getDate() - dow)

  const weeks: Array<Array<{ date: string; count: number; month: number }>> = []
  const monthLabels: Array<{ label: string; weekIdx: number }> = []

  let cur = new Date(start)
  let prevMonth = -1

  for (let w = 0; w < 53; w++) {
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

  return { weeks, monthLabels }
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
      <p class="text-sm font-medium text-muted-foreground">{{ widget.title }}</p>
      <span v-if="!loading" class="text-xs text-muted-foreground">{{ totalCount }} записів / рік</span>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="grid gap-0.5" style="grid-template-columns: repeat(53, 1fr)">
        <div v-for="i in 53*7" :key="i" class="size-2.5 rounded-sm bg-muted animate-pulse" />
      </div>
    </div>

    <template v-else>
      <!-- Month labels -->
      <div class="relative h-4 mb-0.5 shrink-0" style="padding-left: 20px">
        <span
          v-for="ml in grid.monthLabels" :key="ml.weekIdx"
          class="absolute text-[9px] text-muted-foreground font-medium"
          :style="{ left: `${20 + ml.weekIdx * 12}px` }"
        >{{ ml.label }}</span>
      </div>

      <!-- Grid -->
      <div class="flex gap-0.5 overflow-hidden flex-1 items-start">
        <!-- Day labels -->
        <div class="flex flex-col gap-0.5 shrink-0 pr-0.5">
          <div v-for="d in ['Пн','','Ср','','Пт','','Нд']" :key="d"
            class="h-2.5 text-[8px] text-muted-foreground leading-none flex items-center">
            {{ d }}
          </div>
        </div>

        <!-- Weeks -->
        <div class="flex gap-0.5">
          <div v-for="(week, wi) in grid.weeks" :key="wi" class="flex flex-col gap-0.5">
            <div
              v-for="cell in week" :key="cell.date"
              :title="`${cell.date}: ${cell.count}`"
              :class="['size-2.5 rounded-sm transition-colors', cellColor(cell.count)]"
            />
          </div>
        </div>
      </div>

      <!-- Legend -->
      <div class="flex items-center gap-1 mt-2 shrink-0 justify-end">
        <span class="text-[9px] text-muted-foreground">Мало</span>
        <div v-for="lvl in [0, 0.25, 0.5, 0.75, 1]" :key="lvl"
          :class="['size-2.5 rounded-sm', lvl === 0 ? 'bg-muted/50' : lvl < 0.5 ? 'bg-primary/' + Math.round(lvl*100) : 'bg-primary']" />
        <span class="text-[9px] text-muted-foreground">Багато</span>
      </div>
    </template>
  </div>
</template>
