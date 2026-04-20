<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DocField } from '@/types'
import { CalendarIcon, X } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const open = ref(false)
const isDisabled = computed(() => !!(props.disabled || props.field.read_only))

const dateObj = computed<Date | null>(() => {
  const v = props.modelValue as string | null | undefined
  if (!v) return null
  try {
    const d = new Date(v.replace(' ', 'T'))
    return isNaN(d.getTime()) ? null : d
  } catch { return null }
})

const displayLabel = computed(() => {
  const d = dateObj.value
  if (!d) return null
  const day = String(d.getDate()).padStart(2, '0')
  const mon = String(d.getMonth() + 1).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${day}.${mon}.${d.getFullYear()} ${h}:${mi}`
})

function toISO(d: Date): string {
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${mo}-${day} ${h}:${mi}:00`
}

function onSelect(val: unknown) {
  const d = val as Date | null
  if (!d) return
  emit('update:modelValue', toISO(d))
}

function clearValue(e: Event) {
  e.stopPropagation()
  emit('update:modelValue', null)
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <button
        type="button"
        :disabled="isDisabled"
        :class="cn(
          'flex h-9 w-full items-center justify-start gap-2 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-50',
          error ? 'border-destructive focus-visible:ring-destructive' : 'hover:border-ring/40',
          !dateObj && 'text-muted-foreground',
        )"
      >
        <CalendarIcon class="size-4 text-muted-foreground shrink-0" />
        <span class="flex-1 text-left truncate">
          {{ displayLabel ?? (field.placeholder || 'Оберіть дату та час...') }}
        </span>
        <button
          v-if="dateObj && !isDisabled"
          type="button"
          class="ml-auto shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          @click="clearValue"
        >
          <X class="size-3.5" />
        </button>
      </button>
    </PopoverTrigger>

    <PopoverContent class="w-auto p-0" align="start">
      <DatePicker
        :model-value="dateObj"
        inline
        show-time
        hour-format="24"
        :disabled="isDisabled"
        @update:model-value="onSelect"
      />
    </PopoverContent>
  </Popover>
</template>
