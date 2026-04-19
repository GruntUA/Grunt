<script setup lang="ts">
import PrimeAccordionPanel from 'primevue/accordionpanel'
import { cn } from '@/lib/utils'

const props = defineProps<{
  value: string
  class?: string
}>()
</script>

<template>
  <PrimeAccordionPanel
    :value="props.value"
    data-slot="accordion-item"
    :class="cn('border-b last:border-b-0', props.class)"
  >
    <slot />
  </PrimeAccordionPanel>
</template>
