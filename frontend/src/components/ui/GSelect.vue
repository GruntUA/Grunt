<template>
  <div>
    <label v-if="label" :for="id" class="block text-sm font-medium leading-6 text-gray-900 mb-2">
      {{ label }}
    </label>
    <select
      :id="id"
      :value="modelValue"
      :disabled="disabled"
      @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
      :class="[
        'block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 shadow-sm ring-1 ring-inset focus:ring-2 focus:ring-inset sm:text-sm sm:leading-6 transition-colors',
        error
          ? 'ring-red-300 focus:ring-red-500 text-red-900'
          : 'ring-gray-300 focus:ring-primary-600'
      ]"
    >
      <option v-for="option in normalizedOptions" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
    <p v-if="error" class="mt-2 text-sm text-red-600">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'

const props = withDefaults(defineProps<{
  modelValue?: string | number
  label?: string
  options: any[]
  error?: string
  disabled?: boolean
}>(), {
  options: () => [],
  disabled: false
})

const emit = defineEmits(['update:modelValue'])
const id = useId()

const normalizedOptions = computed(() => {
  return props.options.map(opt => {
    if (typeof opt === 'string' || typeof opt === 'number') {
      return { label: String(opt), value: opt }
    }
    return opt
  })
})
</script>
