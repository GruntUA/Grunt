<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardWidget } from '@/types'

const props = defineProps<{
  widget: DashboardWidget
  data: { days: Record<string, number> } | null
  loading?: boolean
}>()

// Show current month
const now = new Date()
const year = now.getFullYear()
const month = now.getMonth() // 0-indexed

const MONTHS_UK = ['Січень', 'Лютий', 'Березень', 'Квітень', 'Травень', 'Червень',
  'Липень', 'Серпень', 'Вересень', 'Жовтень', 'Листопад', 'Грудень']
const DAYS_UK = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']

const monthLabel = computed(() => `${MONTHS_UK[month]} ${year}`)

// Build calendar grid (Mon-first)
const calendarDays = computed(() => {
  const firstDay = new Date(year, month, 1)
  const lastDay = new Date(year, month + 1, 0)

  // Monday-first offset (0=Mon, 6=Sun)
  let startOffset = (firstDay.getDay() + 6) % 7
  const days: Array<{ date: string; day: number; count: number; isToday: boolean } | null> = []

  // Leading nulls
  for (let i = 0; i < startOffset; i++) days.push(null)

  const todayStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

  for (let d = 1; d <= lastDay.getDate(); d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    days.push({
      date: dateStr,
      day: d,
      count: props.data?.days[dateStr] ?? 0,
      isToday: dateStr === todayStr,
    })
  }

  return days
})

function dotColor(count: number): string {
  if (count === 0) return ''
  if (count < 3) return 'bg-primary/40'
  if (count < 8) return 'bg-primary/70'
  return 'bg-primary'
}
</script>

<template>
  <div class="flex flex-col h-full px-4 py-3">
    <!-- Header -->
    <div class="flex items-center justify-between mb-3 shrink-0">
      <p class="text-sm font-medium text-muted-foreground">{{ widget.title }}</p>
      <span class="text-xs font-semibold text-foreground">{{ monthLabel }}</span>
    </div>

    <!-- Skeleton -->
    <div v-if="loading" class="flex-1 grid grid-cols-7 gap-1">
      <div v-for="i in 35" :key="i" class="aspect-square rounded bg-muted animate-pulse" />
    </div>

    <template v-else>
      <!-- Weekday headers -->
      <div class="grid grid-cols-7 mb-1 shrink-0">
        <div v-for="d in DAYS_UK" :key="d" class="text-center text-[10px] font-bold text-muted-foreground/60 uppercase">
          {{ d }}
        </div>
      </div>

      <!-- Days grid -->
      <div class="grid grid-cols-7 gap-0.5 flex-1">
        <div v-for="(cell, i) in calendarDays" :key="i"
          class="flex flex-col items-center justify-center rounded-md text-xs aspect-square"
          :class="cell?.isToday ? 'bg-primary/10 ring-1 ring-primary/40' : (cell ? 'hover:bg-muted/50' : '')">
          <template v-if="cell">
            <span class="leading-none" :class="cell.isToday ? 'font-bold text-primary' : 'text-foreground/70'">
              {{ cell.day }}
            </span>
            <div v-if="cell.count > 0" :class="['mt-0.5 size-1 rounded-full', dotColor(cell.count)]" />
          </template>
        </div>
      </div>

      <!-- Legend -->
      <div class="flex items-center justify-end gap-3 mt-2 shrink-0">
        <div class="flex items-center gap-1 text-[10px] text-muted-foreground">
          <div class="size-2 rounded-full bg-primary/40" /> мало
        </div>
        <div class="flex items-center gap-1 text-[10px] text-muted-foreground">
          <div class="size-2 rounded-full bg-primary" /> багато
        </div>
      </div>
    </template>
  </div>
</template>
