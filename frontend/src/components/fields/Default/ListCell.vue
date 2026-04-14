<script setup lang="ts">
import type { DocField, DocTypeStatusConfig } from '@/types'

defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

function formatCell(val: unknown): string {
  if (val === null || val === undefined || val === '') return '—'
  return String(val)
}
</script>

<template>
  <span class="text-foreground/90 font-medium">{{ formatCell(value) }}</span>
</template>
