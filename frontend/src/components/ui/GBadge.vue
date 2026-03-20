<script setup lang="ts">
withDefaults(defineProps<{
  label: string
  color?: 'gray' | 'green' | 'blue' | 'yellow' | 'red'
}>(), { color: 'gray' })

const colorClass = {
  gray:   'bg-gray-100 text-gray-700',
  green:  'bg-[--grunt-primary-light] text-[--grunt-primary]',
  blue:   'bg-blue-50 text-blue-700',
  yellow: 'bg-yellow-50 text-yellow-700',
  red:    'bg-red-50 text-[--grunt-danger]',
}
</script>

<template>
  <span :class="['inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', colorClass[color]]">
    {{ label }}
  </span>
</template>
