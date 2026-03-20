<script setup lang="ts">
import { computed, useId } from 'vue'

const props = withDefaults(defineProps<{
  modelValue?: string
  label?: string
  options: string | string[]
  error?: string
  required?: boolean
  disabled?: boolean
}>(), { options: () => [] })

defineEmits<{ 'update:modelValue': [v: string] }>()
const id = useId()

const parsedOptions = computed(() =>
  typeof props.options === 'string'
    ? props.options.split('\n').map(o => o.trim()).filter(Boolean)
    : props.options
)
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :for="id" class="text-sm font-medium text-[--grunt-text-primary]">
      {{ label }}<span v-if="required" class="text-[--grunt-danger] ml-0.5">*</span>
    </label>
    <select
      :id="id"
      :value="modelValue"
      :disabled="disabled"
      :class="[
        'w-full rounded-[--grunt-radius-sm] border px-3 py-2 text-sm bg-[--grunt-surface] transition-colors focus:outline-none focus:ring-2',
        error
          ? 'border-[--grunt-danger] focus:ring-[--grunt-danger]/30'
          : 'border-[--grunt-border] focus:ring-[--grunt-primary]/30 focus:border-[--grunt-primary]',
        disabled ? 'opacity-50 cursor-not-allowed' : '',
      ]"
      @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option value="">— оберіть —</option>
      <option v-for="opt in parsedOptions" :key="opt" :value="opt">{{ opt }}</option>
    </select>
    <p v-if="error" class="text-xs text-[--grunt-danger]">{{ error }}</p>
  </div>
</template>
