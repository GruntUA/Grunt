<script setup lang="ts">
// A MultiLink filter picks linked documents just like a Link one; the backend
// matches them against the junction table (any of the picked values).
import type { DocField } from '@/types'
import LinkFilterInput from '@/components/fields/Link/FilterInput.vue'

defineProps<{
  field: DocField
  modelValue: string
  displayValue: string
  op: string
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:displayValue': [value: string]
  'submit': []
}>()
</script>

<template>
  <LinkFilterInput
    :field
    :model-value
    :display-value
    :op
    :placeholder
    @update:model-value="(v: string) => emit('update:modelValue', v)"
    @update:display-value="(v: string) => emit('update:displayValue', v)"
    @submit="emit('submit')"
  />
</template>
