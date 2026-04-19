<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = withDefaults(defineProps<{
  orientation?: 'horizontal' | 'vertical'
  decorative?: boolean
  class?: HTMLAttributes["class"]
}>(), {
  orientation: 'horizontal',
  decorative: true,
})
</script>

<template>
  <div
    data-slot="separator"
    :role="decorative ? 'none' : 'separator'"
    :aria-orientation="orientation"
    :class="cn(
      'bg-border shrink-0',
      orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
      props.class,
    )"
  />
</template>
