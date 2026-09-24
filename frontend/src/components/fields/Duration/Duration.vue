<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import { Input } from '@/components/ui/input'

const props = defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

function onUpdate(v: string | number) {
  if (v === '' || v == null) return emit('update:modelValue', null)
  const n = Number(v)
  emit('update:modelValue', Number.isFinite(n) ? n : null)
}

// A focused number input changes its value when you scroll over it — silent
// data corruption. Swallow the wheel while focused; page scroll still works
// when the field isn't focused.
function onWheel(e: WheelEvent) {
  if (document.activeElement === e.target) e.preventDefault()
}

// Stored value is seconds — show a human-readable breakdown alongside the
// raw number so entering e.g. "9000" is legible without doing the math.
const readable = computed(() => {
  const total = props.modelValue
  if (total == null || !Number.isFinite(total)) return ''
  const s = Math.abs(Math.round(total))
  const days = Math.floor(s / 86400)
  const hours = Math.floor((s % 86400) / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  const seconds = s % 60
  const parts: string[] = []
  if (days) parts.push(`${days} д`)
  if (hours) parts.push(`${hours} год`)
  if (minutes) parts.push(`${minutes} хв`)
  if (seconds || !parts.length) parts.push(`${seconds} с`)
  return parts.join(' ')
})
</script>

<template>
  <div>
    <Input
      type="number"
      step="1"
      min="0"
      inputmode="numeric"
      :model-value="modelValue ?? ''"
      :placeholder="field.placeholder ?? '0'"
      :required="field.required"
      :disabled="disabled || field.read_only"
      :max="field.max_value"
      :aria-invalid="error ? true : undefined"
      :class="['w-full tabular-nums', field.bold && 'font-medium']"
      @wheel="onWheel"
      @update:model-value="onUpdate"
    />
    <p v-if="readable" class="mt-1 text-muted-foreground tabular-nums">{{ readable }}</p>
  </div>
</template>
