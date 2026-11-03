<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CalendarDate, getLocalTimeZone, type DateValue } from '@internationalized/date'
import { CalendarIcon } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { dateFormatSpec } from '@/core/datetime'

const props = defineProps<{
  modelValue: Date | null
  placeholder?: string
  disabled?: boolean
  invalid?: boolean
  showTime?: boolean
  class?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Date | null]
}>()

// Layout of the typed value (separator, part order, placeholder) follows
// SystemSettings.date_format.
const PART_WIDTH = { y: 4, m: 2, d: 2 } as const
const spec = computed(() => dateFormatSpec())
const placeholderText = computed(() => props.placeholder ?? spec.value.placeholder)

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
    if (props.showTime) {
      // Keep the existing time; for an empty field use the current time, not midnight
      const t = props.modelValue ?? new Date()
      jsDate.setHours(t.getHours(), t.getMinutes(), props.modelValue ? t.getSeconds() : 0)
    }
    emit('update:modelValue', jsDate)
  },
})

function pad(n: number, w = 2) { return String(n).padStart(w, '0') }

function partOf(d: Date, p: 'd' | 'm' | 'y'): string {
  if (p === 'y') return String(d.getFullYear())
  return p === 'm' ? pad(d.getMonth() + 1) : pad(d.getDate())
}

function formatText(d: Date | null): string {
  if (!d) return ''
  let s = spec.value.order.map((p) => partOf(d, p)).join(spec.value.sep)
  if (props.showTime) s += ` ${pad(d.getHours())}:${pad(d.getMinutes())}`
  return s
}

const displayText = computed(() => formatText(props.modelValue))

function setTime(h: number, m: number) {
  const base = props.modelValue ? new Date(props.modelValue) : new Date()
  base.setHours(h, m, 0, 0)
  emit('update:modelValue', base)
}

const hours = computed({
  get: () => pad((props.modelValue ?? new Date()).getHours()),
  set: (v: string) => setTime(Number(v), (props.modelValue ?? new Date()).getMinutes()),
})
const minutes = computed({
  get: () => pad((props.modelValue ?? new Date()).getMinutes()),
  set: (v: string) => setTime((props.modelValue ?? new Date()).getHours(), Number(v)),
})

// --- Клавіатурний ввід ---
const text = ref(displayText.value)

// Синхронізуємо текст із зовнішнім значенням, поки поле не редагують
watch(displayText, (v) => { if (!focused.value) text.value = v })

function applyMask(raw: string): string {
  const { sep, order } = spec.value
  const dateDigits = 8 // d(2)+m(2)+y(4) in any order
  const digits = raw.replace(/\D/g, '').slice(0, dateDigits + (props.showTime ? 4 : 0))

  const parts: string[] = []
  let i = 0
  for (const p of order) {
    if (i >= digits.length) break
    parts.push(digits.slice(i, i + PART_WIDTH[p]))
    i += PART_WIDTH[p]
  }
  let out = parts.join(sep)
  if (digits.length > dateDigits) {
    out += ' ' + digits.slice(dateDigits, dateDigits + 2)
    if (digits.length > dateDigits + 2) out += ':' + digits.slice(dateDigits + 2, dateDigits + 4)
  }
  return out
}

function onInput(e: Event) {
  text.value = applyMask((e.target as HTMLInputElement).value)
}

function parseText(s: string): Date | null {
  const { sep, order } = spec.value
  const escSep = sep.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const groups = order.map((p) => `(\\d{1,${PART_WIDTH[p]}})`).join(escSep)
  const m = s.trim().match(new RegExp(`^${groups}(?:\\s+(\\d{1,2}):(\\d{1,2}))?$`))
  if (!m) return null

  const val: Record<'d' | 'm' | 'y', number> = { d: 0, m: 0, y: 0 }
  order.forEach((p, idx) => { val[p] = Number(m[idx + 1]) })
  const { d: day, m: month, y: year } = val
  const hh = m[order.length + 1] != null ? Number(m[order.length + 1]) : (props.modelValue?.getHours() ?? 0)
  const mi = m[order.length + 2] != null ? Number(m[order.length + 2]) : (props.modelValue?.getMinutes() ?? 0)
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
    // The new value, not displayText: the prop hasn't caught up yet, and Enter
    // commits again on the blur that follows — it must not re-commit the old date.
    if (parsed.getTime() !== props.modelValue?.getTime()) emit('update:modelValue', parsed)
    text.value = formatText(parsed)
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
      :placeholder="placeholderText"
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
          class="w-14 rounded-md border border-input bg-transparent px-2 py-1 text-center outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
        <span class="text-muted-foreground">:</span>
        <input
          type="number" min="0" max="59" v-model="minutes"
          class="w-14 rounded-md border border-input bg-transparent px-2 py-1 text-center outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
      </div>
    </PopoverContent>
  </Popover>
</template>
