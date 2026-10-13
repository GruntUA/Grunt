<script setup lang="ts">
import { useId } from 'vue'
import type { BaseFieldProps } from '@/types'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

defineProps<BaseFieldProps>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const id = useId()
</script>

<template>
  <div class="flex items-center gap-2">
    <Checkbox
      :id="id"
      :model-value="!!modelValue"
      :disabled="disabled || field.read_only"
      :aria-invalid="error ? true : undefined"
      @update:model-value="emit('update:modelValue', $event === true)"
    />
    <Label :for="id" :class="error && 'text-destructive'">
      {{ field.label }}
      <span v-if="field.required" class="text-destructive">*</span>
    </Label>
  </div>
</template>
