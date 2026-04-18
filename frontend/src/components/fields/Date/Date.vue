<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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

const dateValue = computed<DateValue | undefined>(() => {
  const v = props.modelValue as string | null | undefined
  if (!v) return undefined
  try {
    return parseDate(v.substring(0, 10))
  } catch {
    return undefined
  }
})

// Text shown in the input (DD.MM.YYYY)
const inputText = ref('')
const isEditing = ref(false)
const open = ref(false)

function formatForInput(val: DateValue | undefined): string {
  if (!val) return ''
  const d = String(val.day).padStart(2, '0')
  const m = String(val.month).padStart(2, '0')
  const y = val.year
  return `${d}.${m}.${y}`
}

watch(
  dateValue,
  (val) => {
    if (!isEditing.value) {
      inputText.value = formatForInput(val)
    }
  },
  { immediate: true },
)

// Parse DD.MM.YYYY, DD/MM/YYYY, or YYYY-MM-DD → ISO string
function parseInputText(text: string): string | null {
  const dmy = text.match(/^(\d{1,2})[.,/](\d{1,2})[.,/](\d{4})$/)
  if (dmy) {
    const [, d, m, y] = dmy
    const iso = `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`
    try { parseDate(iso); return iso } catch { return null }
  }

  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (iso) {
    try { parseDate(text); return text } catch { return null }
  }

  return null
}

function onFocus() {
  isEditing.value = true
}

function onBlur() {
  isEditing.value = false
  const text = inputText.value.trim()
  if (!text) {
    emit('update:modelValue', null)
    inputText.value = ''
    return
  }
  const iso = parseInputText(text)
  if (iso) {
    emit('update:modelValue', iso)
    inputText.value = formatForInput(parseDate(iso))
  } else {
    // Revert to last valid value
    inputText.value = formatForInput(dateValue.value)
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    (e.target as HTMLInputElement).blur()
  }
  if (e.key === 'Escape') {
    isEditing.value = false
    inputText.value = formatForInput(dateValue.value)
    ;(e.target as HTMLInputElement).blur()
  }
}

function onSelect(val: DateValue | undefined) {
  if (!val) return
  emit('update:modelValue', val.toString())
  inputText.value = formatForInput(val)
  open.value = false
}

function clearValue(e: Event) {
  e.stopPropagation()
  emit('update:modelValue', null)
  inputText.value = ''
}

const defaultPlaceholder = today(getLocalTimeZone())
const isDisabled = computed(() => !!(props.disabled || props.field.read_only))
</script>

<template>
  <div
    :class="cn(
      'flex h-9 w-full items-center gap-1 rounded-md border border-input bg-transparent px-2 py-1 text-sm shadow-sm transition-colors',
      'focus-within:outline-none focus-within:ring-1 focus-within:ring-ring',
      isDisabled && 'cursor-not-allowed opacity-50',
      error ? 'border-destructive focus-within:ring-destructive' : 'hover:border-ring/40',
    )"
  >
    <!-- Calendar icon opens the popover -->
    <Popover v-model:open="open">
      <PopoverTrigger as-child>
        <button
          type="button"
          :disabled="isDisabled"
          class="shrink-0 text-muted-foreground hover:text-foreground transition-colors disabled:pointer-events-none"
          tabindex="-1"
        >
          <CalendarIcon class="size-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent class="w-auto p-0" align="start">
        <Calendar
          :model-value="dateValue"
          :default-placeholder="defaultPlaceholder"
          :disabled="isDisabled"
          @update:model-value="onSelect($event)"
        />
      </PopoverContent>
    </Popover>

    <!-- Text input -->
    <input
      v-model="inputText"
      type="text"
      :placeholder="field.placeholder || 'ДД.ММ.РРРР'"
      :disabled="isDisabled"
      class="flex-1 min-w-0 bg-transparent outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
      @focus="onFocus"
      @blur="onBlur"
      @keydown="onKeydown"
    />

    <!-- Clear button -->
    <button
      v-if="dateValue && !isDisabled"
      type="button"
      class="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
      tabindex="-1"
      @click="clearValue"
    >
      <X class="size-3.5" />
    </button>
  </div>
</template>
