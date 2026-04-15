<script setup lang="ts">
import { type DateValue, getLocalTimeZone, today } from '@internationalized/date'
import {
  CalendarRoot,
  CalendarHeader,
  CalendarHeading,
  CalendarGrid,
  CalendarGridHead,
  CalendarGridRow,
  CalendarHeadCell,
  CalendarGridBody,
  CalendarCell,
  CalendarCellTrigger,
  CalendarNext,
  CalendarPrev,
} from 'reka-ui'
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import { cn } from '@/lib/utils'

defineProps<{
  modelValue?: DateValue
  defaultPlaceholder?: DateValue
  disabled?: boolean
  initialFocus?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: DateValue | undefined]
}>()
</script>

<template>
  <CalendarRoot
    v-slot="{ grid, weekDays }"
    :model-value="modelValue"
    :default-placeholder="defaultPlaceholder ?? today(getLocalTimeZone())"
    :disabled="disabled"
    layout="month-and-year"
    :class="cn('p-3', $attrs.class as string)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <CalendarHeader class="flex items-center justify-between mb-2">
      <CalendarPrev
        class="inline-flex items-center justify-center size-7 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 disabled:pointer-events-none"
      >
        <ChevronLeft class="size-4" />
      </CalendarPrev>
      <CalendarHeading class="text-sm font-semibold text-foreground" />
      <CalendarNext
        class="inline-flex items-center justify-center size-7 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 disabled:pointer-events-none"
      >
        <ChevronRight class="size-4" />
      </CalendarNext>
    </CalendarHeader>

    <CalendarGrid v-for="month in grid" :key="String(month.value)" class="w-full border-collapse space-y-1">
      <CalendarGridHead>
        <CalendarGridRow class="flex">
          <CalendarHeadCell
            v-for="day in weekDays"
            :key="day"
            class="w-8 rounded-md text-[0.8rem] font-normal text-muted-foreground text-center"
          >
            {{ day }}
          </CalendarHeadCell>
        </CalendarGridRow>
      </CalendarGridHead>

      <CalendarGridBody class="[&>tr>td]:p-0">
        <CalendarGridRow
          v-for="(weekDates, idx) in month.rows"
          :key="idx"
          class="flex mt-2 w-full"
        >
          <CalendarCell
            v-for="weekDate in weekDates"
            :key="String(weekDate)"
            :date="weekDate"
            class="relative size-8 p-0 text-center text-sm focus-within:relative focus-within:z-20"
          >
            <CalendarCellTrigger
              :day="weekDate"
              :month="month.value"
              :class="cn(
                'inline-flex size-8 items-center justify-center rounded-md text-sm font-normal transition-colors',
                'hover:bg-accent hover:text-accent-foreground',
                'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
                'data-[selected]:bg-primary data-[selected]:text-primary-foreground data-[selected]:hover:bg-primary data-[selected]:hover:text-primary-foreground',
                'data-[today]:bg-accent data-[today]:text-accent-foreground',
                'data-[outside-month]:text-muted-foreground/40 data-[outside-month]:pointer-events-none',
                'data-[disabled]:opacity-50 data-[disabled]:pointer-events-none',
                'data-[unavailable]:line-through data-[unavailable]:opacity-30',
              )"
            />
          </CalendarCell>
        </CalendarGridRow>
      </CalendarGridBody>
    </CalendarGrid>
  </CalendarRoot>
</template>
