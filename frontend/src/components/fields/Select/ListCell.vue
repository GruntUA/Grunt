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

type GenericBadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline' | 'gray' | 'blue' | 'green' | 'yellow' | 'orange' | 'red' | 'purple' | 'pink'

function getColorVariant(color: string): GenericBadgeVariant {
  const allowed = ['gray', 'blue', 'green', 'yellow', 'orange', 'red', 'purple', 'pink']
  return allowed.includes(color) ? (color as GenericBadgeVariant) : 'outline'
}

const badge = computed(() => {
  if (props.value === null || props.value === undefined || props.value === '') return null
  const val = String(props.value)
  const isStatusField = props.statusConfig?.field === props.field.fieldname
  if (isStatusField && props.statusConfig?.indicators) {
    const ind = props.statusConfig.indicators.find((i) => i.value === val)
    if (ind) {
      return { variant: getColorVariant(ind.color), label: ind.label ?? val }
    }
  }
  return { variant: 'outline' as const, label: val }
})
</script>

<template>
  <Badge v-if="badge" :variant="badge.variant" class="font-normal whitespace-nowrap">
    {{ badge.label }}
  </Badge>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
