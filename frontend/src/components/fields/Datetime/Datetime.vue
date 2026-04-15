<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DocField } from '@/types'
import { DateFormatter, getLocalTimeZone, parseDate, today } from '@internationalized/date'
import type { DateValue } from '@internationalized/date'
import { CalendarIcon, X } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Calendar } from '@/components/ui/calendar'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const df = new DateFormatter('uk-UA', { dateStyle: 'long' })

// Parse stored value (ISO "YYYY-MM-DD HH:mm:ss" or "YYYY-MM-DDTHH:mm")
const parsed = computed(() => {
  const v = props.modelValue as string | null | undefined
  if (!v) return { date: undefined, time: '00:00' }
  const norm = v.replace(' ', 'T')
  const [datePart, timePart] = norm.split('T')
  let date: DateValue | undefined
  try { date = parseDate(datePart) } catch { /* noop */ }
  const time = timePart?.slice(0, 5) ?? '00:00'
  return { date, time }
})

const dateValue = computed(() => parsed.value.date)
const timeValue = computed(() => parsed.value.time)

// When calendar picks a date, keep the existing time
const open = ref(false)

function onDateSelect(val: DateValue | undefined) {
  if (!val) return
  emit('update:modelValue', `${val.toString()} ${timeValue.value}:00`)
  open.value = false
}

// When time input changes, keep current date
function onTimeChange(e: Event) {
  const t = (e.target as HTMLInputElement).value
  if (!dateValue.value) return
  emit('update:modelValue', `${dateValue.value.toString()} ${t}:00`)
}

function clearValue(e: Event) {
  e.stopPropagation()
  emit('update:modelValue', null)
}

const displayLabel = computed(() => {
  if (!dateValue.value) return null
  const datePart = df.format(dateValue.value.toDate(getLocalTimeZone()))
  return `${datePart} ${timeValue.value}`
})

const defaultPlaceholder = today(getLocalTimeZone())
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <button
        type="button"
        :disabled="disabled || field.read_only"
        :class="cn(
          'flex h-9 w-full items-center justify-start gap-2 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-50',
          error ? 'border-destructive focus-visible:ring-destructive' : 'hover:border-ring/40',
          !dateValue && 'text-muted-foreground',
        )"
      >
        <CalendarIcon class="size-4 text-muted-foreground shrink-0" />
        <span class="flex-1 text-left truncate">
          {{ displayLabel ?? (field.placeholder || 'Оберіть дату та час...') }}
        </span>
        <button
          v-if="dateValue && !disabled && !field.read_only"
          type="button"
          class="ml-auto shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          @click="clearValue"
        >
          <X class="size-3.5" />
        </button>
      </button>
    </PopoverTrigger>

    <PopoverContent class="w-auto p-0" align="start">
      <Calendar
        :model-value="dateValue"
        :default-placeholder="defaultPlaceholder"
        :disabled="disabled || field.read_only"
        @update:model-value="onDateSelect($event)"
      />
      <!-- Time input at the bottom of the calendar popover -->
      <div class="border-t border-border px-3 py-2 flex items-center gap-2">
        <span class="text-xs text-muted-foreground font-medium min-w-[40px]">Час:</span>
        <input
          type="time"
          :value="timeValue"
          :disabled="disabled || field.read_only || !dateValue"
          class="flex-1 h-8 rounded-md border border-input bg-transparent px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
          @change="onTimeChange"
        />
      </div>
    </PopoverContent>
  </Popover>
</template>
