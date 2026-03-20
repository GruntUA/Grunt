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

function autoResize(el: HTMLTextAreaElement) {
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <label :for="id" class="text-sm font-medium text-[--grunt-text-primary]">
      {{ field.label }}<span v-if="field.required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>
    <textarea
      :id="id"
      :value="String(modelValue ?? '')"
      :placeholder="field.placeholder ?? ''"
      :disabled="disabled || field.read_only"
      rows="3"
      class="w-full rounded-[--grunt-radius-sm] border border-[--grunt-border] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[--grunt-primary]/30 focus:border-[--grunt-primary] resize-none overflow-hidden disabled:bg-[--grunt-surface-secondary] disabled:text-[--grunt-text-secondary]"
      :class="{ 'border-[--grunt-danger]': error }"
      @input="(e) => { emit('update:modelValue', (e.target as HTMLTextAreaElement).value); autoResize(e.target as HTMLTextAreaElement) }"
      @focus="(e) => autoResize(e.target as HTMLTextAreaElement)"
    />
    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
    <p v-else-if="field.description" class="text-xs text-[--grunt-text-muted]">{{ field.description }}</p>
  </div>
</template>
