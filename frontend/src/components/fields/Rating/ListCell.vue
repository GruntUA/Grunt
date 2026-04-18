<script setup lang="ts">
import type { DocField, DocTypeStatusConfig } from '@/types'

defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()
</script>

<template>
  <template v-if="value !== null && value !== undefined && value !== ''">
    <span class="inline-flex items-center gap-0.5">
      <template v-for="i in 5" :key="i">
        <svg v-if="Number(value) >= i" xmlns="http://www.w3.org/2000/svg" class="size-3.5 text-amber-400" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
        </svg>
        <svg v-else-if="Number(value) >= i - 0.5" xmlns="http://www.w3.org/2000/svg" class="size-3.5" viewBox="0 0 24 24">
          <defs>
            <linearGradient :id="`hstar-${String(row.id)}-${i}`">
              <stop offset="50%" stop-color="#fbbf24"/>
              <stop offset="50%" style="stop-color: var(--border)"/>
            </linearGradient>
          </defs>
          <path :fill="`url(#hstar-${String(row.id)}-${i})`" d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
        </svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" class="size-3.5 text-border" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
        </svg>
      </template>
      <span class="ml-1 text-xs text-muted-foreground tabular-nums">
        {{ Number(value).toFixed(1).replace(/\.0$/, '') }}
      </span>
    </span>
  </template>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
