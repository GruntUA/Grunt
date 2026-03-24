<script setup lang="ts">
import type { DocField } from '@/types'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
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
      :checked="!!modelValue"
      :disabled="disabled || field.read_only"
      @update:checked="emit('update:modelValue', $event)"
    />
    <Label :for="id" class="text-sm font-medium cursor-pointer select-none">{{ field.label }}</Label>
  </div>
</template>
