<script setup lang="ts">
import type { DocField, DocTypeStatusConfig } from '@/types'

defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

function formatDate(val: unknown): string {
  if (!val) return '—'
  const str = String(val).replace(' ', 'T')
  const d = new Date(str)
  if (isNaN(d.getTime())) return String(val)
  return d.toLocaleDateString('uk-UA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  })
}
</script>

<template>
  <span class="text-muted-foreground tabular-nums">{{ formatDate(value) }}</span>
</template>
