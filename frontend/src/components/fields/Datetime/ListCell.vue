<script setup lang="ts">
import type { DocField, DocTypeStatusConfig } from '@/types'
import { formatDateTime } from '@/core/datetime'

defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()
</script>

<template>
  <span class="text-muted-foreground tabular-nums">{{ formatDateTime(value as string | null) }}</span>
</template>
