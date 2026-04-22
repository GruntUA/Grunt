<script setup lang="ts">
import { computed } from 'vue'
import type { DocField, DocTypeStatusConfig } from '@/types'

const props = defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

const COLOR_CLASSES: Record<string, string> = {
  default: '',
  secondary: 'border-muted-foreground/20 bg-muted/40 text-muted-foreground',
  success: 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-emerald-400',
  info: 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400',
  warn: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400',
  danger: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400',
  contrast: 'border-foreground/20 bg-foreground text-background',
  // Legacy colors for backward compatibility.
  gray: 'border-muted-foreground/20 bg-muted/40 text-muted-foreground',
  blue: 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400',
  green: 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-emerald-400',
  yellow: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400',
  orange: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400',
  red: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400',
  purple: 'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300',
  pink: 'border-pink-500/30 bg-pink-500/10 text-pink-700 dark:text-pink-300',
}

const badge = computed(() => {
  if (props.value === null || props.value === undefined || props.value === '') return null
  const val = String(props.value)
  const isStatusField = props.statusConfig?.field === props.field.fieldname
  if (isStatusField && props.statusConfig?.indicators) {
    const ind = props.statusConfig.indicators.find((i) => i.value === val)
    if (ind) {
      return { colorClass: COLOR_CLASSES[ind.color] ?? '', label: ind.label ?? val }
    }
  }
  return { colorClass: '', label: val }
})
</script>

<template>
  <Badge v-if="badge" severity="contrast" :class="['font-normal whitespace-nowrap', badge.colorClass]">
    {{ badge.label }}
  </Badge>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
