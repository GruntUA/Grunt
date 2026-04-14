<script setup lang="ts">
import { Input } from '@/components/ui/input'
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
  <Input
    :model-value="modelValue"
    class="h-8 text-xs mb-3"
    :placeholder="op === 'like' ? 'частина тексту...' : 'Значення'"
    @update:model-value="emit('update:modelValue', String($event))"
    @keydown.enter="emit('submit')"
  />
</template>
