<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import { CalendarDate, DateFormatter, getLocalTimeZone, parseDate, today } from '@internationalized/date'
import type { DateValue } from '@internationalized/date'
import { CalendarIcon, X } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
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

// Formatter for display (Ukrainian locale)
const df = new DateFormatter('uk-UA', { dateStyle: 'long' })

// Convert ISO string (YYYY-MM-DD) → DateValue
const dateValue = computed<DateValue | undefined>(() => {
  const v = props.modelValue as string | null | undefined
  if (!v) return undefined
  try {
    return parseDate(v.substring(0, 10))
  } catch {
    return undefined
  }
})

// Convert DateValue → ISO string
function onSelect(val: DateValue | undefined, close: () => void) {
  if (!val) return
  emit('update:modelValue', val.toString())
  close()
}

function clearValue(e: Event) {
  e.stopPropagation()
  emit('update:modelValue', null)
}

const displayLabel = computed(() => {
  if (!dateValue.value) return null
  return df.format(dateValue.value.toDate(getLocalTimeZone()))
})

const defaultPlaceholder = today(getLocalTimeZone())
</script>

<template>
  <Popover v-slot="{ close }">
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
          {{ displayLabel ?? (field.placeholder || 'Оберіть дату...') }}
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
        @update:model-value="onSelect($event, close)"
      />
    </PopoverContent>
  </Popover>
</template>
