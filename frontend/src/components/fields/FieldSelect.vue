<script setup lang="ts">
import type { DocField } from '@/types'
import GSelect from '@/components/ui/GSelect.vue'

defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
</script>

<template>
  <GSelect
    :model-value="String(modelValue ?? '')"
    :label="field.label"
    :options="field.options ?? ''"
    :required="field.required"
    :disabled="disabled || field.read_only"
    :error="error"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
