<script setup lang="ts">
import type { DocField } from '@/types'

defineProps<{
  field: DocField
  modelValue: number | null | undefined
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()
</script>

<template>
  <InputNumber
    :model-value="modelValue"
    :minFractionDigits="2"
    :maxFractionDigits="9"
    :placeholder="field.placeholder ?? '0.0'"
    :required="field.required"
    :disabled="disabled || field.read_only"
    class="w-full"
    fluid
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
