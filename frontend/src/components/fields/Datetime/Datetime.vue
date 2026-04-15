<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'
import { Input } from '@/components/ui/input'

const props = defineProps<{
  field: DocField;
  modelValue: unknown;
  disabled?: boolean;
  error?: string;
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const formattedValue = computed(() => {
  if (!props.modelValue) return ''
  const val = String(props.modelValue).replace(' ', 'T')
  // datetime-local expects YYYY-MM-DDTHH:mm
  return val.length >= 16 ? val.slice(0, 16) : val
})
</script>

<template>
  <Input :model-value="formattedValue" type="datetime-local" :required="field.required"
    :disabled="disabled || field.read_only" @update:model-value="emit('update:modelValue', $event || null)" />
</template>
