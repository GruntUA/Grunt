<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { DocField } from '@/types'
import { CalendarIcon, X } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const open = ref(false)
const inputText = ref('')
const isEditing = ref(false)
const isDisabled = computed(() => !!(props.disabled || props.field.read_only))

const dateObj = computed<Date | null>(() => {
  const v = props.modelValue as string | null | undefined
  if (!v) return null
  try {
    const [y, m, d] = v.substring(0, 10).split('-').map(Number)
    return new Date(y, m - 1, d)
  } catch { return null }
})

function formatForInput(d: Date | null): string {
  if (!d) return ''
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`
}

function toISO(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

watch(dateObj, (val) => {
  if (!isEditing.value) inputText.value = formatForInput(val)
}, { immediate: true })

function parseInputText(text: string): Date | null {
  const dmy = text.match(/^(\d{1,2})[.,\/](\d{1,2})[.,\/](\d{4})$/)
  if (dmy) {
    const d = new Date(Number(dmy[3]), Number(dmy[2]) - 1, Number(dmy[1]))
    return isNaN(d.getTime()) ? null : d
  }
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (iso) {
    const d = new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]))
    return isNaN(d.getTime()) ? null : d
  }
  return null
}

function onFocus() { isEditing.value = true }

function onBlur() {
  isEditing.value = false
  const text = inputText.value.trim()
  if (!text) { emit('update:modelValue', null); inputText.value = ''; return }
  const d = parseInputText(text)
  if (d) {
    emit('update:modelValue', toISO(d))
    inputText.value = formatForInput(d)
  } else {
    inputText.value = formatForInput(dateObj.value)
  }
}

function onKeydown(e: KeyboardEvent) {
  const el = e.target as HTMLInputElement
  if (e.key === 'Enter') el.blur()
  if (e.key === 'Escape') {
    isEditing.value = false
    inputText.value = formatForInput(dateObj.value)
    el.blur()
  }
}

function onSelect(val: unknown) {
  const d = val as Date | null
  if (!d) return
  emit('update:modelValue', toISO(d))
  inputText.value = formatForInput(d)
  open.value = false
}

function clearValue(e: Event) {
  e.stopPropagation()
  emit('update:modelValue', null)
  inputText.value = ''
}
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
        <DatePicker
          :model-value="dateObj"
          inline
          :disabled="isDisabled"
          @update:model-value="onSelect($event as Date | null)"
        />
      </PopoverContent>
    </Popover>

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

    <button
      v-if="dateObj && !isDisabled"
      type="button"
      class="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
      tabindex="-1"
      @click="clearValue"
    >
      <X class="size-3.5" />
    </button>
  </div>
</template>
