<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const parsedOptions = computed(() =>
  typeof props.field.options === 'string'
    ? props.field.options.split('\n').map(o => o.trim()).filter(Boolean)
    : (props.field.options ?? [])
)
</script>

<template>
  <Select :model-value="String(modelValue ?? '')" @update:model-value="emit('update:modelValue', $event)">
    <SelectTrigger :disabled="disabled || field.read_only">
      <SelectValue placeholder="— оберіть —" />
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="opt in parsedOptions" :key="opt" :value="opt">{{ opt }}</SelectItem>
    </SelectContent>
  </Select>
</template>
