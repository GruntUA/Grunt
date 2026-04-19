<script setup lang="ts">
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: string }>()
</script>

<template>
  <div
    data-slot="dialog-footer"
    :class="cn('flex flex-col-reverse gap-2 p-6 sm:flex-row sm:justify-end border-t bg-muted/5 mt-1', props.class)"
  >
    <slot />
  </div>
</template>
