<script setup lang="ts">
import type { DocField } from '@/types'
defineProps<{ field: DocField }>()
</script>

<template>
  <div class="rounded-md border border-border h-12 flex items-end px-3 pb-1.5 bg-background overflow-hidden relative">
    <svg viewBox="0 0 200 40" class="w-full h-8 text-foreground/40" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M10 30 Q30 10 50 28 Q70 46 90 20 Q110 -5 130 25 Q150 50 170 22 Q185 10 190 18" />
    </svg>
    <div class="absolute bottom-0 left-3 right-3 border-b border-dashed border-muted-foreground/30" />
  </div>
</template>
