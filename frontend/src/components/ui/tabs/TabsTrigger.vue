<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import PrimeTab from 'primevue/tab'
import { cn } from '@/lib/utils'

const props = defineProps<{
  value: string
  disabled?: boolean
  variant?: string
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <PrimeTab
    data-slot="tabs-trigger"
    :value="value"
    :disabled="disabled"
    :class="cn('', props.class)"
  >
    <slot />
  </PrimeTab>
</template>
