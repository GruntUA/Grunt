<script setup lang="ts">
import { computed } from 'vue'
import type { DocField } from '@/types'

const props = defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
}>()

const values = computed<string[]>(() => {
  const v = props.value
  if (Array.isArray(v)) return v as string[]
  if (typeof v === 'string' && v) {
    try { return JSON.parse(v) as string[] } catch { return [] }
  }
  return []
})
</script>

<template>
  <div v-if="values.length" class="flex flex-wrap gap-1">
    <Badge
      v-for="val in values"
      :key="val"
      variant="secondary"
      class="font-normal whitespace-nowrap"
    >{{ val }}</Badge>
  </div>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
