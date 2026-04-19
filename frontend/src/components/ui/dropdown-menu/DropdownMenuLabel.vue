<script setup lang="ts">
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: string, inset?: boolean }>()
</script>

<template>
  <div
    data-slot="dropdown-menu-label"
    :data-inset="inset || undefined"
    :class="cn('px-2 py-1.5 text-sm font-medium data-[inset]:pl-8', props.class)"
  >
    <slot />
  </div>
</template>
