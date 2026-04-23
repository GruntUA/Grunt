<script setup lang="ts">
import type { DocField } from '@/types'

defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
</script>

<template>
  <InputText
    :model-value="String(modelValue ?? '')"
    :placeholder="field.placeholder ?? field.label"
    :required="field.required"
    :disabled="disabled || field.read_only"
    class="w-full"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
