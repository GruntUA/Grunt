<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'

const props = defineProps<{
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

const options = computed(() => {
  if (!props.field.options) return []
  return typeof props.field.options === 'string'
    ? props.field.options.split('\n').map((o) => o.trim()).filter(Boolean)
    : (props.field.options as string[])
})
</script>

<template>
  <div class="flex flex-wrap gap-1 max-h-32 overflow-y-auto mb-3">
    <button
      v-for="opt in options"
      :key="opt"
      type="button"
      class="px-2 py-1 text-xs rounded-md border transition-colors"
      :class="modelValue === opt
        ? 'border-primary bg-primary/10 text-primary font-semibold'
        : 'border-border hover:border-primary/40'"
      @click="emit('update:modelValue', opt)"
    >{{ opt }}</button>
  </div>
</template>
