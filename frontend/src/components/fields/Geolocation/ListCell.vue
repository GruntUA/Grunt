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
  <template v-if="value && typeof value === 'object'">
    <span class="tabular-nums text-muted-foreground font-mono">
      {{ Number((value as any).lat).toFixed(5) }},
      {{ Number((value as any).lng).toFixed(5) }}
    </span>
  </template>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
