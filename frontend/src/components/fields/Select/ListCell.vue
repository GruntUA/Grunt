<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import type { Component } from 'vue'
import type { DocField, DocTypeStatusConfig } from '@/types'
import { Badge } from '@/components/ui/badge'
import { statusToneClass } from '@/core/status'

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

const badge = computed(() => {
  if (props.value === null || props.value === undefined || props.value === '') return null
  const val = String(props.value)
  const ind = props.statusConfig?.field === props.field.fieldname
    ? props.statusConfig.indicators.find((i) => i.value === val)
    : undefined
  return { class: statusToneClass(ind?.color), label: ind?.label || val, icon: ind?.icon ?? null }
})
</script>

<template>
  <Badge
    v-if="badge"
    variant="outline"
    :class="['font-normal gap-1.5', badge.class]"
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
