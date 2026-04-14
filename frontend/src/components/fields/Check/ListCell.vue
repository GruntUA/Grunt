<script setup lang="ts">
import { Check } from '@lucide/vue'
import type { DocField, DocTypeStatusConfig } from '@/types'

defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()
</script>

<template>
  <Check v-if="value" class="size-4 text-emerald-500" />
  <span v-else class="text-muted-foreground/30">—</span>
</template>
