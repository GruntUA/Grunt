<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CalendarDate, getLocalTimeZone, type DateValue } from '@internationalized/date'
import { CalendarIcon } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'

const props = withDefaults(defineProps<{
  modelValue: Date | null
  placeholder?: string
  disabled?: boolean
  invalid?: boolean
  showTime?: boolean
  class?: string
}>(), {
  placeholder: 'ДД.ММ.РРРР',
})

const emit = defineEmits<{ 'update:modelValue': [value: Date | null] }>()

const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)
const wrapperEl = ref<HTMLElement | null>(null)
const focused = ref(false)

function openCalendar() {
  if (props.disabled) return
  anchorEl.value = wrapperEl.value
  isOpen.value = !isOpen.value
}

const calendarValue = computed<DateValue | null>({
  get() {
    const d = props.modelValue
    if (!d) return null
    return new CalendarDate(d.getFullYear(), d.getMonth() + 1, d.getDate())
  },
  set(val) {
    if (!val) { emit('update:modelValue', null); return }
    const jsDate = val.toDate(getLocalTimeZone())
    if (props.showTime && props.modelValue) {
      jsDate.setHours(props.modelValue.getHours(), props.modelValue.getMinutes(), props.modelValue.getSeconds())
    }
    emit('update:modelValue', jsDate)
  },
})

function pad(n: number) { return String(n).padStart(2, '0') }

const displayText = computed(() => {
  const d = props.modelValue
  if (!d) return ''
  let s = `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`
  if (props.showTime) s += ` ${pad(d.getHours())}:${pad(d.getMinutes())}`
  return s
})

function setTime(h: number, m: number) {
  const base = props.modelValue ? new Date(props.modelValue) : new Date()
  base.setHours(h, m, 0, 0)
  emit('update:modelValue', base)
}

const hours = computed({
  get: () => props.modelValue ? pad(props.modelValue.getHours()) : '00',
  set: (v: string) => setTime(Number(v), props.modelValue?.getMinutes() ?? 0),
})
const minutes = computed({
  get: () => props.modelValue ? pad(props.modelValue.getMinutes()) : '00',
  set: (v: string) => setTime(props.modelValue?.getHours() ?? 0, Number(v)),
})

// --- Клавіатурний ввід ---
const text = ref(displayText.value)

// Синхронізуємо текст із зовнішнім значенням, поки поле не редагують
watch(displayText, (v) => { if (!focused.value) text.value = v })

function applyMask(raw: string): string {
  let digits = raw.replace(/\D/g, '').slice(0, props.showTime ? 12 : 8)
  let out = digits.slice(0, 2)
  if (digits.length > 2) out += '.' + digits.slice(2, 4)
  if (digits.length > 4) out += '.' + digits.slice(4, 8)
  if (digits.length > 8) out += ' ' + digits.slice(8, 10)
  if (digits.length > 10) out += ':' + digits.slice(10, 12)
  return out
}

function onInput(e: Event) {
  text.value = applyMask((e.target as HTMLInputElement).value)
}

function parseText(s: string): Date | null {
  const m = s.trim().match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{1,2}))?$/)
  if (!m) return null
  const day = Number(m[1]), month = Number(m[2]), year = Number(m[3])
  const hh = m[4] != null ? Number(m[4]) : (props.modelValue?.getHours() ?? 0)
  const mi = m[5] != null ? Number(m[5]) : (props.modelValue?.getMinutes() ?? 0)
  if (month < 1 || month > 12 || day < 1 || day > 31 || hh > 23 || mi > 59) return null
  const d = new Date(year, month - 1, day, hh, mi, 0, 0)
  if (isNaN(d.getTime()) || d.getDate() !== day || d.getMonth() !== month - 1) return null
  return d
}

function commit() {
  focused.value = false
  const s = text.value.trim()
  if (!s) {
    if (props.modelValue) emit('update:modelValue', null)
    text.value = ''
    return
  }
  const parsed = parseText(s)
  if (parsed) {
    emit('update:modelValue', parsed)
    text.value = displayText.value
  } else {
    // Некоректний ввід — повертаємо останнє валідне значення
    text.value = displayText.value
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    commit()
    ;(e.target as HTMLInputElement).blur()
  } else if (e.key === 'Escape') {
    text.value = displayText.value
    ;(e.target as HTMLInputElement).blur()
  }
}
</script>

<template>
  <div
    ref="wrapperEl"
    :class="cn(
      'border-input dark:bg-input/30 flex h-9 w-full items-center gap-2 rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs transition-[color,box-shadow]',
      'focus-within:border-ring focus-within:ring-ring/50 focus-within:ring-3',
      disabled && 'cursor-not-allowed opacity-60',
      invalid && 'border-destructive focus-within:ring-destructive/20',
      props.class,
    )"
  >
    <input
      type="text"
      inputmode="numeric"
      :value="text"
      :disabled="disabled"
      :placeholder="placeholder"
      class="text-foreground placeholder:text-muted-foreground w-full min-w-0 bg-transparent outline-none disabled:cursor-not-allowed"
      @focus="focused = true"
      @input="onInput"
      @blur="commit"
      @keydown="onKeydown"
    >
    <button
      type="button"
      tabindex="-1"
      :disabled="disabled"
      class="text-muted-foreground hover:text-foreground shrink-0 outline-none disabled:cursor-not-allowed"
      @click="openCalendar"
    >
      <CalendarIcon class="size-4 opacity-70" />
    </button>
  </div>

  <Popover v-model:open="isOpen">
    <PopoverAnchor :reference="anchorEl ?? undefined" />
    <PopoverContent class="w-auto p-0">
      <Calendar v-model="calendarValue" />
      <div v-if="showTime" class="flex items-center justify-center gap-2 border-t border-border p-3">
        <input
          type="number" min="0" max="23" v-model="hours"
          class="w-14 rounded-md border border-input bg-transparent px-2 py-1 text-sm text-center outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
        <span class="text-muted-foreground">:</span>
        <input
          type="number" min="0" max="59" v-model="minutes"
          class="w-14 rounded-md border border-input bg-transparent px-2 py-1 text-sm text-center outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
      </div>
    </PopoverContent>
  </Popover>
</template>
