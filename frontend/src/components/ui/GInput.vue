<template>
  <div>
    <label v-if="label" :for="id" class="block text-sm font-medium leading-6 text-gray-900 mb-2">
      {{ label }}
    </label>
    <div class="relative">
      <input
        :id="id"
        :type="type"
        :value="modelValue"
        :disabled="disabled"
        :placeholder="placeholder"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
        :class="[
          'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset focus:ring-2 focus:ring-inset sm:text-sm sm:leading-6 transition-colors',
          error 
            ? 'ring-red-300 placeholder:text-red-300 focus:ring-red-500 text-red-900' 
            : 'ring-gray-300 placeholder:text-gray-400 focus:ring-primary-600'
        ]"
      />
      <div v-if="error" class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3">
        <svg class="h-5 w-5 text-red-500" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd" />
        </svg>
      </div>
    </div>
    <p v-if="error" class="mt-2 text-sm text-red-600">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { useId } from 'vue'

withDefaults(defineProps<{
  modelValue?: string | number
  label?: string
  error?: string
  type?: string
  placeholder?: string
  disabled?: boolean
}>(), {
  type: 'text',
  disabled: false
})

const emit = defineEmits(['update:modelValue'])
const id = useId()
</script>
