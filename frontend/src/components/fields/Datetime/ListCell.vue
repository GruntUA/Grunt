<script setup lang="ts">
import type { DocField, DocTypeStatusConfig } from '@/types'

const props = defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

function formatDatetime(val: unknown): string {
  if (!val) return '—'
  try {
    const d = new Date(String(val))
    if (isNaN(d.getTime())) return String(val)
    return d.toLocaleString('uk-UA', { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return String(val)
  }
}
</script>

<template>
  <span class="text-muted-foreground tabular-nums">{{ formatDatetime(value) }}</span>
</template>
