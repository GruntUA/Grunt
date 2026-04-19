<script setup lang="ts">
import PrimeAccordionContent from 'primevue/accordioncontent'
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: string }>()
</script>

<template>
  <PrimeAccordionContent data-slot="accordion-content">
    <div :class="cn('pt-0 pb-4 text-sm', props.class)">
      <slot />
    </div>
  </PrimeAccordionContent>
</template>
