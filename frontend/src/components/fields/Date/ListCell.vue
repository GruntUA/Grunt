<script setup lang="ts">
import type { DocField, DocTypeStatusConfig } from '@/types'
import { formatDate } from '@/core/datetime'

defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()
</script>

<template>
  <span class="text-muted-foreground tabular-nums">{{ formatDate(value as string | null) }}</span>
</template>
