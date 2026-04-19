<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import PrimeTabList from 'primevue/tablist'
import { cn } from '@/lib/utils'

const props = defineProps<{
  variant?: string
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <PrimeTabList
    data-slot="tabs-list"
    :class="cn('', props.class)"
  >
    <slot />
  </PrimeTabList>
</template>
