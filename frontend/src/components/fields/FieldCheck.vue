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
    <label :for="id" class="flex items-center gap-2 cursor-pointer select-none">
      <div class="relative">
        <input
          :id="id"
          type="checkbox"
          :checked="!!modelValue"
          :disabled="disabled || field.read_only"
          class="sr-only"
          @change="emit('update:modelValue', ($event.target as HTMLInputElement).checked)"
        />
        <div
          class="w-4 h-4 rounded border-2 flex items-center justify-center transition-colors"
          :class="modelValue
            ? 'bg-[--grunt-primary] border-[--grunt-primary]'
            : 'bg-white border-[--grunt-border-strong]'"
        >
          <svg v-if="modelValue" class="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 12 10">
            <path d="M1 5l4 4 6-8" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
      </div>
      <span class="text-sm font-medium text-[--grunt-text-primary]">{{ field.label }}</span>
    </label>
    <p v-if="error" class="text-xs text-[--grunt-danger] ml-6">{{ error }}</p>
  </div>
</template>
