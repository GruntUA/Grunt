<script setup lang="ts">
import { useId } from 'vue'
import type { BaseFieldProps } from '@/types'
import { Checkbox } from '@/components/ui/checkbox'

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
    <label
      :for="id"
      class="cursor-pointer select-none font-medium"
      :class="error ? 'text-destructive' : 'text-foreground/90'"
    >
      {{ field.label }}
      <span v-if="field.required" class="text-destructive font-semibold">*</span>
    </label>
  </div>
</template>
