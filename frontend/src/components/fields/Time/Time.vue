<script setup lang="ts">
import type { BaseFieldProps } from '@/types'
import { Input } from '@/components/ui/input'

defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

// Native <input type=time> works in minute precision; normalise a picked
// "HH:MM" back to the "HH:MM:SS" the backend stores so the value shape stays
// consistent. An untouched value keeps whatever seconds it already had.
function onUpdate(v: string | number) {
  const s = String(v ?? '')
  if (!s) return emit('update:modelValue', null)
  emit('update:modelValue', s.length === 5 ? `${s}:00` : s)
}
</script>

<template>
  <Input
    type="time"
    :model-value="String(modelValue ?? '')"
    :placeholder="field.placeholder ?? undefined"
    :required="field.required"
    :disabled="disabled || field.read_only"
    :aria-invalid="error ? true : undefined"
    :aria-label="field.label"
    class="w-full tabular-nums"
    @update:model-value="onUpdate"
  />
</template>
