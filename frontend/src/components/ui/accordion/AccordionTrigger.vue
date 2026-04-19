<script setup lang="ts">
import PrimeAccordionHeader from 'primevue/accordionheader'
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: string }>()
</script>

<template>
  <PrimeAccordionHeader
    data-slot="accordion-trigger"
    :class="cn('flex flex-1 items-start justify-between gap-4 py-4 text-left text-sm font-medium transition-all hover:underline', props.class)"
  >
    <slot />
  </PrimeAccordionHeader>
</template>
