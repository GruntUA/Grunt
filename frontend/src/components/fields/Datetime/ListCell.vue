<script setup lang="ts">
import type { DocField, DocTypeStatusConfig } from '@/types'

defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

function formatDatetime(val: unknown): string {
  if (!val) return '—'
  const str = String(val).replace(' ', 'T')
  const d = new Date(str)
  if (isNaN(d.getTime())) return String(val)
  return d.toLocaleString('uk-UA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>

<template>
  <span class="text-muted-foreground tabular-nums">{{ formatDatetime(value) }}</span>
</template>
