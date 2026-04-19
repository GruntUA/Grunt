<script setup lang="ts">
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: string }>()
</script>

<template>
  <h2
    data-slot="dialog-title"
    :class="cn('text-xl font-bold tracking-tight text-foreground', props.class)"
  >
    <slot />
  </h2>
</template>
