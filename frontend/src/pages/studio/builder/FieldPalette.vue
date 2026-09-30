<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { shallowRef } from 'vue'
import type { Component } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { useBuilderStore } from '@/stores/builder'
import { getPaletteGroups, getLayoutFields } from '@/core/fieldRegistry'
import type { FieldDefinition } from '@/core/fieldRegistry'
import type { DocField } from '@/types'
import { loadLucideLib } from '@/lib/lucide'

const { t } = useI18n()

// ── Lucide icon resolution ────────────────────────────────────────────────────
type IconMap = Record<string, Component>
const lucideIcons = shallowRef<IconMap>({})
let lucideLoaded = false

function loadLucide() {
  if (lucideLoaded) return
  lucideLoaded = true
  loadLucideLib().then(lib => { lucideIcons.value = lib })
}
loadLucide()

function getLucideIcon(icon: string): Component | null {
  if (!icon || !/^[a-z][a-z0-9-]+$/.test(icon)) return null
  const pascal = icon.split('-').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('')
  return (lucideIcons.value[pascal] as Component) ?? null
}

const builder = useBuilderStore()

const fieldGroups = getPaletteGroups()
const layoutItems = getLayoutFields()

function cloneField(item: FieldDefinition): DocField {
  return {
    fieldname: builder.generateFieldname(item.type),
    label: item.label,
    fieldtype: item.type,
  }
}

function addLayoutItem(type: string) {
  if (type === 'Tab') {
    builder.addTab()
  } else if (type === 'Section') {
    builder.addField('Section')
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto p-3 border-r border-border bg-background">
    <p class="font-semibold text-muted-foreground/70 uppercase tracking-wide mb-3 px-1">Fields</p>

    <!-- Draggable field groups (from registry) -->
    <div v-for="group in fieldGroups" :key="group.category" class="mb-4">
      <p class="text-muted-foreground/70 px-1 mb-1">{{ group.category }}</p>
      <VueDraggable
        :model-value="group.fields"
        :group="{ name: 'builder-fields', pull: 'clone', put: false }"
        :sort="false"
        :clone="cloneField"
        class="flex flex-col gap-0.5"
      >
        <div
          v-for="item in group.fields"
          :key="item.type"
          class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-border transition-colors text-left w-full cursor-grab active:cursor-grabbing"
        >
          <span class="w-5 flex items-center justify-center shrink-0 text-muted-foreground">
            <component :is="getLucideIcon(item.icon)" v-if="getLucideIcon(item.icon)" class="size-4" />
            <span v-else class="text-base">{{ item.icon }}</span>
          </span>
          <span class="text-foreground">{{ item.label }}</span>
        </div>
      </VueDraggable>
    </div>

    <!-- Layout items (click only, from registry) -->
    <div class="mb-4">
      <p class="text-muted-foreground/70 px-1 mb-1">{{ t('Structural') }}</p>
      <div class="flex flex-col gap-0.5">
        <button
          v-for="item in layoutItems"
          :key="item.type"
          type="button"
          class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-border transition-colors text-left w-full"
          @click="addLayoutItem(item.type)"
        >
          <span class="w-5 flex items-center justify-center shrink-0 text-muted-foreground">
            <component :is="getLucideIcon(item.icon)" v-if="getLucideIcon(item.icon)" class="size-4" />
            <span v-else class="text-base">{{ item.icon }}</span>
          </span>
          <span class="text-foreground">{{ item.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
