<script setup lang="ts">
import { computed } from 'vue'
import type { DocField, DocTypeStatusConfig } from '@/types'
import { durationUnit, formatDuration } from '@/core/duration'

const props = defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

// Two largest units keep the column narrow; the tooltip has the full breakdown.
const short = computed(() => formatDuration(props.value, durationUnit(props.field), 2))
const full = computed(() => formatDuration(props.value, durationUnit(props.field)))
</script>

<template>
  <span class="text-foreground/90 font-medium tabular-nums whitespace-nowrap" :title="full !== short ? full : undefined">
    {{ short || '—' }}
  </span>
</template>
