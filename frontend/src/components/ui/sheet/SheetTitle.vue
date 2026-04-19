<script setup lang="ts">
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: string }>()
</script>

<template>
  <h2 data-slot="sheet-title" :class="cn('text-foreground font-semibold', props.class)">
    <slot />
  </h2>
</template>
