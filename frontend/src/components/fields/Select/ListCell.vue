<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import type { DocField, DocTypeStatusConfig } from '@/types'

const props = defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

const colorToBadge: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; class?: string }> = {
  gray: { variant: 'outline' },
  blue: { variant: 'outline', class: 'border-blue-400 text-blue-700 bg-blue-50' },
  green: { variant: 'outline', class: 'border-green-500 text-green-700 bg-green-50' },
  yellow: { variant: 'outline', class: 'border-yellow-400 text-yellow-700 bg-yellow-50' },
  orange: { variant: 'outline', class: 'border-orange-400 text-orange-700 bg-orange-50' },
  red: { variant: 'destructive' },
  purple: { variant: 'outline', class: 'border-purple-400 text-purple-700 bg-purple-50' },
  pink: { variant: 'outline', class: 'border-pink-400 text-pink-700 bg-pink-50' },
}

const badge = computed(() => {
  if (props.value === null || props.value === undefined || props.value === '') return null
  const val = String(props.value)
  const isStatusField = props.statusConfig?.field === props.field.fieldname
  if (isStatusField && props.statusConfig?.indicators) {
    const ind = props.statusConfig.indicators.find((i) => i.value === val)
    if (ind) {
      const b = colorToBadge[ind.color] ?? { variant: 'outline' as const }
      return { ...b, label: ind.label ?? val }
    }
  }
  return { variant: 'outline' as const, label: val }
})
</script>

<template>
  <Badge v-if="badge" :variant="badge.variant" class="font-normal whitespace-nowrap" :class="badge.class">
    {{ badge.label }}
  </Badge>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
