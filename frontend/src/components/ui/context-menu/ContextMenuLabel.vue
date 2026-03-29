<script setup lang="ts">
import type { ContextMenuLabelProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { ContextMenuLabel } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<ContextMenuLabelProps & { class?: HTMLAttributes['class']; inset?: boolean }>()
</script>

<template>
  <ContextMenuLabel
    :class="cn('px-2 py-1.5 text-xs font-semibold text-muted-foreground', inset && 'pl-8', props.class)"
  >
    <slot />
  </ContextMenuLabel>
</template>
