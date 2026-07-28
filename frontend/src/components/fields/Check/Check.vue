<script setup lang="ts">
import type { DocField } from '@/types'
import { useId } from 'vue'

defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
const id = useId()
</script>

<template>
  <div class="flex items-center gap-2">
    <Checkbox
      :id="id"
      :model-value="!!modelValue"
      :disabled="disabled || field.read_only"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <label :for="id" class="text-sm font-medium cursor-pointer select-none text-foreground/90">{{ field.label }}</label>
  </div>
</template>
