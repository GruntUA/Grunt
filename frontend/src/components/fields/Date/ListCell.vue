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
  try {
    const d = new Date(String(val))
    if (isNaN(d.getTime())) return String(val)
    return d.toLocaleDateString('uk-UA')
  } catch {
    return String(val)
  }
}
</script>

<template>
  <span class="text-muted-foreground tabular-nums">{{ formatDate(value) }}</span>
</template>
