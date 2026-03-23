<script setup lang="ts">
import type { DocField } from '@/types'
import { Input } from '@/components/ui/input'

defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
</script>

<template>
  <Input
    :model-value="modelValue !== null && modelValue !== undefined ? String(modelValue) : ''"
    type="number"
    step="1"
    :placeholder="field.placeholder ?? '0'"
    :required="field.required"
    :disabled="disabled || field.read_only"
    @update:model-value="emit('update:modelValue', $event === '' ? null : Number($event))"
  />
</template>
