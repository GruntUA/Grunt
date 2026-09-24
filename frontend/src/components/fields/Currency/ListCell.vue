<script setup lang="ts">
import type { DocField, DocTypeStatusConfig } from '@/types'
import { currencyCode, formatCurrency } from '@/core/currency'

defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()
</script>

<template>
  <span class="text-foreground/90 font-medium tabular-nums whitespace-nowrap">
    {{ formatCurrency(value, currencyCode(field, row)) || '—' }}
  </span>
</template>
