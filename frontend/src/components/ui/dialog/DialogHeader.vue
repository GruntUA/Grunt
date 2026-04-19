<script setup lang="ts">
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: string }>()
</script>

<template>
  <div
    data-slot="dialog-header"
    :class="cn('flex flex-col gap-1.5 p-6 text-center sm:text-left bg-muted/5 border-b mb-1', props.class)"
  >
    <slot />
  </div>
</template>
