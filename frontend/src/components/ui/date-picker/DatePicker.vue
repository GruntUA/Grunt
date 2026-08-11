<script setup lang="ts">
import { computed, ref } from 'vue'
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
  placeholder: 'Оберіть дату',
})

const emit = defineEmits<{ 'update:modelValue': [value: Date | null] }>()

const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)

function toggle(event: Event) {
  if (props.disabled) return
  if (isOpen.value) { isOpen.value = false; return }
  anchorEl.value = event.currentTarget as HTMLElement
  isOpen.value = true
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
</script>

<template>
  <button
    type="button"
    :disabled="disabled"
    :class="cn(
      'border-input text-foreground dark:bg-input/30 dark:hover:bg-input/50 flex h-9 w-full items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] hover:bg-accent/50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3 disabled:cursor-not-allowed disabled:opacity-60',
      !modelValue && 'text-muted-foreground',
      invalid && 'border-destructive focus-visible:ring-destructive/20',
      props.class,
    )"
    @click="toggle"
  >
    <span class="truncate">{{ displayText || placeholder }}</span>
    <CalendarIcon class="size-4 shrink-0 opacity-50" />
  </button>

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
