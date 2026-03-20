<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), {
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  type: 'button',
})

defineEmits<{ click: [e: MouseEvent] }>()

const sizeClass = { sm: 'px-3 py-1.5 text-xs', md: 'px-4 py-2 text-sm', lg: 'px-5 py-2.5 text-base' }
const variantClass = {
  primary:   'bg-[--grunt-primary] text-white hover:bg-[--grunt-primary-hover] border border-transparent',
  secondary: 'bg-white text-[--grunt-text-primary] border border-[--grunt-border-strong] hover:border-[--grunt-primary]',
  danger:    'bg-[--grunt-danger] text-white border border-transparent hover:opacity-90',
  ghost:     'bg-transparent text-[--grunt-text-secondary] border border-transparent hover:bg-[--grunt-surface-secondary]',
}
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :class="[
      'inline-flex items-center justify-center font-medium rounded-[--grunt-radius-sm] transition-colors focus:outline-none focus:ring-2 focus:ring-[--grunt-primary]/40',
      sizeClass[size],
      variantClass[variant],
      (disabled || loading) ? 'opacity-50 cursor-not-allowed' : '',
    ]"
    @click="$emit('click', $event)"
  >
    <svg v-if="loading" class="animate-spin -ml-1 mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
    <slot />
  </button>
</template>
