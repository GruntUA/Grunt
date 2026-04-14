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
  <div class="flex gap-2 mb-3">
    <button
      type="button"
      class="flex-1 py-1.5 text-xs rounded border transition-colors"
      :class="modelValue === '1'
        ? 'border-primary bg-primary/10 text-primary font-semibold'
        : 'border-border hover:border-primary/40 text-muted-foreground'"
      @click="emit('update:modelValue', '1')"
    >✓ Так</button>
    <button
      type="button"
      class="flex-1 py-1.5 text-xs rounded border transition-colors"
      :class="modelValue === '0'
        ? 'border-primary bg-primary/10 text-primary font-semibold'
        : 'border-border hover:border-primary/40 text-muted-foreground'"
      @click="emit('update:modelValue', '0')"
    >✗ Ні</button>
  </div>
</template>
