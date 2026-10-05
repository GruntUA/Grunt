<script setup lang="ts">
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

// A focused number input changes its value when you scroll over it - silent
// data corruption. Swallow the wheel while focused; page scroll still works
// when the field isn't focused.
function onWheel(e: WheelEvent) {
  if (document.activeElement === e.target) e.preventDefault()
}
</script>

<template>
  <Input
    type="number"
    step="any"
    inputmode="decimal"
    :model-value="modelValue ?? ''"
    :placeholder="field.placeholder ?? '0.0'"
    :required="field.required"
    :disabled="disabled || field.read_only"
    :min="field.min_value"
    :max="field.max_value"
    :aria-invalid="error ? true : undefined"
    :class="['w-full tabular-nums', field.bold && 'font-medium']"
    @wheel="onWheel"
    @update:model-value="onUpdate"
  />
</template>
