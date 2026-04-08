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
    :model-value="String(modelValue ?? '')"
    type="datetime-local"
    :required="field.required"
    :disabled="disabled || field.read_only"
    @update:model-value="emit('update:modelValue', $event || null)"
  />
</template>
