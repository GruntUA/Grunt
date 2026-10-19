<script setup lang="ts">
import type { DocField, DocTypeStatusConfig } from '@/types'
import { formatBytes, isBytesField } from '@/core/bytes'

defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

function formatCell(val: unknown, field: DocField): string {
  if (val === null || val === undefined || val === '') return '—'
  return isBytesField(field) ? formatBytes(Number(val)) : String(val)
}
</script>

<template>
  <span class="text-foreground/90 font-medium" :class="isBytesField(field) && 'tabular-nums whitespace-nowrap'">
    {{ formatCell(value, field) }}
  </span>
</template>
