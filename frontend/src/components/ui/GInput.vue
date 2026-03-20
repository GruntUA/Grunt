<script setup lang="ts">
import { useId } from 'vue'

withDefaults(defineProps<{
  modelValue?: string | number
  label?: string
  placeholder?: string
  error?: string
  hint?: string
  required?: boolean
  disabled?: boolean
  type?: string
}>(), { type: 'text' })

defineEmits<{ 'update:modelValue': [v: string] }>()
const id = useId()
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :for="id" class="text-sm font-medium text-[--grunt-text-primary]">
      {{ label }}<span v-if="required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>
    <input
      :id="id"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :class="[
        'w-full rounded-[--grunt-radius-sm] border px-3 py-2 text-sm bg-[--grunt-surface] transition-colors focus:outline-none focus:ring-2',
        error
          ? 'border-[--grunt-danger] focus:ring-[--grunt-danger]/30'
          : 'border-[--grunt-border] focus:ring-[--grunt-primary]/30 focus:border-[--grunt-primary]',
        disabled ? 'opacity-50 cursor-not-allowed bg-[--grunt-surface-secondary]' : '',
      ]"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
    <p v-else-if="hint" class="text-xs text-[--grunt-text-muted]">{{ hint }}</p>
  </div>
</template>
