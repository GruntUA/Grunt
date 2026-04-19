<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import PrimeTabPanel from 'primevue/tabpanel'
import { cn } from '@/lib/utils'

const props = defineProps<{
  value: string
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <PrimeTabPanel
    data-slot="tabs-content"
    :value="value"
    :class="cn('', props.class)"
  >
    <slot />
  </PrimeTabPanel>
</template>
