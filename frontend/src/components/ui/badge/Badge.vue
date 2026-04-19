<script setup lang="ts">
import PrimeBadge from 'primevue/badge'

defineProps<{
  severity?: 'secondary' | 'info' | 'success' | 'warn' | 'danger' | 'contrast'
  size?: 'small' | 'large' | 'xlarge'
  value?: string | number
  class?: string | string[]
}>()
</script>

<template>
  <PrimeBadge
    data-slot="badge"
    v-bind="$props"
  >
    <slot />
  </PrimeBadge>
</template>
