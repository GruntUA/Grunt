<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = withDefaults(defineProps<{
  size?: 'sm' | 'md' | 'lg'
  class?: HTMLAttributes["class"]
}>(), { size: 'md' })

const sizeClass = { sm: 'size-4', md: 'size-6', lg: 'size-10' }
</script>

<template>
  <svg
    :class="cn('animate-spin text-primary', sizeClass[size], props.class)"
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
  </svg>
</template>
