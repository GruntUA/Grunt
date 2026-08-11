<script setup lang="ts">
import { shallowRef } from 'vue'
import type { Component } from 'vue'
import type { DocField, DocTypeStatusConfig } from '@/types'
import { initials } from '@/core/composables/usePresence'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

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
  import('@lucide/vue').then((lib) => { lucideIcons.value = lib as unknown as IconMap })
}

function getIconComponent(name: string): Component | null {
  loadIcons()
  if (!name) return null
  const pascal = name.split('-').map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  return (lucideIcons.value[pascal] ?? null) as Component | null
}

function formatCell(val: unknown): string {
  if (val === null || val === undefined || val === '') return '—'
  return String(val)
}
</script>

<template>
  <span
    v-if="value !== null && value !== undefined && value !== ''"
    class="inline-flex items-center gap-2 text-foreground/90 font-medium"
  >
    <Avatar v-if="(field.fieldname + '__image') in row" class="size-6 shrink-0">
      <AvatarImage v-if="row[field.fieldname + '__image']" :src="row[field.fieldname + '__image'] as string" alt="" />
      <AvatarFallback class="text-xs">
        {{ initials((row[field.fieldname + '__label'] as string) || formatCell(value)) }}
      </AvatarFallback>
    </Avatar>
    <component
      :is="getIconComponent(String(row[field.fieldname + '__icon'] ?? ''))"
      v-else-if="row[field.fieldname + '__icon']"
      class="size-3.5 shrink-0 text-muted-foreground"
    />
    {{ (row[field.fieldname + '__label'] as string) || formatCell(value) }}
  </span>
  <span v-else class="text-muted-foreground/30">—</span>
</template>
