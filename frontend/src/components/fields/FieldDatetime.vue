<script setup lang="ts">
import type { DocField } from '@/types'
import GInput from '@/components/ui/GInput.vue'

defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
</script>

<template>
  <GInput
    :model-value="String(modelValue ?? '')"
    :label="field.label"
    type="datetime-local"
    :required="field.required"
    :disabled="disabled || field.read_only"
    :error="error"
    @update:model-value="emit('update:modelValue', $event || null)"
  />
</template>
