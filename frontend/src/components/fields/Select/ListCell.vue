<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import type { Component } from 'vue'
import type { DocField, DocTypeStatusConfig } from '@/types'
import { Badge } from '@/components/ui/badge'
import type { BadgeVariants } from '@/components/ui/badge'

const props = defineProps<{
  value: unknown
  row: Record<string, unknown>
  field: DocField
  statusConfig?: DocTypeStatusConfig | null
}>()

type IconMap = Record<string, Component>
const lucideIcons = shallowRef<IconMap>({})
let iconsLoaded = false

function loadIcons() {
  if (iconsLoaded) return
  iconsLoaded = true
  import('@lucide/vue').then((lib) => { lucideIcons.value = lib as unknown as IconMap })
}

function getIconComponent(name: string): Component | null {
  loadIcons()
  if (!name) return null
  const pascal = name.split('-').map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  return (lucideIcons.value[pascal] ?? null) as Component | null
}

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

const COLOR_VARIANT: Record<string, BadgeVariants['variant']> = {
  default: undefined,
  secondary: 'secondary',
  success: 'success',
  info: 'info',
  warn: 'warning',
  danger: 'destructive',
  contrast: 'outline',
  // Legacy aliases
  gray: 'secondary',
  blue: 'info',
  green: 'success',
  yellow: 'warning',
  orange: 'warning',
  red: 'destructive',
  purple: undefined,
  pink: undefined,
}

const badge = computed(() => {
  if (props.value === null || props.value === undefined || props.value === '') return null
  const val = String(props.value)
  const isStatusField = props.statusConfig?.field === props.field.fieldname
  if (isStatusField && props.statusConfig?.indicators) {
    const ind = props.statusConfig.indicators.find((i) => i.value === val)
    if (ind) {
      return {
        colorClass: COLOR_CLASSES[ind.color] ?? '',
        variant: COLOR_VARIANT[ind.color],
        label: ind.label ?? val,
        icon: ind.icon ?? null,
      }
    }
  }
  return { colorClass: '', variant: undefined, label: val, icon: null }
})
</script>

<template>
  <Badge
    v-if="badge"
    :variant="badge.variant"
    :class="['font-normal whitespace-nowrap inline-flex items-center gap-1.5', badge.colorClass]"
  >
    <component
      :is="getIconComponent(String(badge.icon ?? ''))"
      v-if="badge.icon"
      class="size-3.5 shrink-0"
    />
    {{ badge.label }}
  </Badge>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
