<script setup lang="ts">
import { useId } from 'vue'
import type { DocField } from '@/types'

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
  <div class="flex flex-col gap-1">
    <label :for="id" class="text-sm font-medium text-[--grunt-text-primary]">
      {{ field.label }}
      <span v-if="field.required" class="text-[--grunt-danger] ml-0.5">*</span>
      <span v-if="field.options" class="text-[--grunt-text-muted] font-normal ml-1 text-xs">({{ field.options }})</span>
    </label>
    <textarea
      :id="id"
      :value="String(modelValue ?? '')"
      :disabled="disabled || field.read_only"
      rows="8"
      spellcheck="false"
      class="w-full rounded-[--grunt-radius-sm] border border-[--grunt-border] px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[--grunt-primary]/30 focus:border-[--grunt-primary] resize-y disabled:bg-[--grunt-surface-secondary] whitespace-pre"
      :class="{ 'border-[--grunt-danger]': error }"
      @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
    />
    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
  </div>
</template>
