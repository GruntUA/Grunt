<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :class="[
      'inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-md transition-all focus-ring shadow-sm',
      variantClasses[variant],
      (disabled || loading) ? 'opacity-60 cursor-not-allowed' : 'hover:-translate-y-px',
      $attrs.class
    ]"
    @click="$emit('click', $event)"
  >
    <svg v-if="loading" class="animate-spin -ml-1 mr-2 h-4 w-4 text-current" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
    <slot></slot>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  type?: 'button' | 'submit' | 'reset'
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  disabled?: boolean
  loading?: boolean
}>(), {
  type: 'button',
  variant: 'primary',
  disabled: false,
  loading: false
})

const emit = defineEmits(['click'])

const variantClasses = {
  primary: 'bg-primary-700 text-white hover:bg-primary-600 border border-transparent',
  secondary: 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-300',
  danger: 'bg-red-600 text-white hover:bg-red-500 border border-transparent focus:ring-red-500/50',
  ghost: 'bg-transparent text-gray-600 hover:bg-gray-100 hover:text-gray-900 border border-transparent shadow-none',
}
</script>
