<script setup lang="ts">
import type { DocField } from '@/types'

defineProps<{
  field: DocField
  modelValue: string
  displayValue: string
  op: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:displayValue': [value: string]
  'submit': []
}>()
</script>

<template>
  <InputText
    :model-value="modelValue"
    type="date"
    class="h-8 text-xs mb-3 w-full"
    @update:model-value="emit('update:modelValue', String($event))"
    @keydown.enter="emit('submit')"
  />
</template>
