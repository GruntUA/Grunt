<script setup lang="ts">
import { shallowRef } from 'vue'
import type { Component } from 'vue'
import type { DocField, DocTypeStatusConfig } from '@/types'

defineProps<{
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
  import('lucide-vue-next').then((lib) => { lucideIcons.value = lib as unknown as IconMap })
}

function getIconComponent(name: string): Component | null {
  loadIcons()
  if (!name) return null
  const pascal = name.split('-').map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  return (lucideIcons.value[pascal] ?? null) as Component | null
}
</script>

<template>
  <template v-if="value">
    <span class="inline-flex items-center gap-1.5 text-foreground/80">
      <component :is="getIconComponent(String(value))" v-if="getIconComponent(String(value))" class="size-4 shrink-0" />
      <span class="text-xs text-muted-foreground">{{ value }}</span>
    </span>
  </template>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
