<script setup lang="ts">
import draggable from 'vuedraggable'
import { useBuilderStore } from '@/stores/builder'
import type { FieldType, DocField } from '@/types'

const builder = useBuilderStore()

interface PaletteItem {
  type: FieldType
  icon: string
  label: string
}

const fieldGroups: { label: string; items: PaletteItem[] }[] = [
  {
    label: 'Базові',
    items: [
      { type: 'Text', icon: 'T', label: 'Text' },
      { type: 'LongText', icon: '¶', label: 'Long Text' },
      { type: 'Int', icon: '#', label: 'Integer' },
      { type: 'Float', icon: '.1', label: 'Float' },
      { type: 'Check', icon: '✓', label: 'Checkbox' },
      { type: 'Color', icon: '🎨', label: 'Color' },
    ],
  },
  {
    label: 'Дата і час',
    items: [
      { type: 'Date', icon: '📅', label: 'Date' },
      { type: 'Datetime', icon: '🕐', label: 'Datetime' },
      { type: 'Time', icon: '⏰', label: 'Time' },
    ],
  },
  {
    label: 'Вибір і зв\'язки',
    items: [
      { type: 'Select', icon: '▼', label: 'Select' },
      { type: 'Link', icon: '🔗', label: 'Link' },
    ],
  },
  {
    label: 'Медіа',
    items: [
      { type: 'Attach', icon: '📎', label: 'Attach' },
      { type: 'Image', icon: '🖼', label: 'Image' },
    ],
  },
  {
    label: 'Текст',
    items: [
      { type: 'RichText', icon: '✍', label: 'Rich Text' },
      { type: 'JSON', icon: '{}', label: 'JSON' },
      { type: 'Code', icon: '<>', label: 'Code' },
    ],
  },
  {
    label: 'Таблиці',
    items: [
      { type: 'Table', icon: '▦', label: 'Table' },
    ],
  },
]

// Layout items are click-only, not draggable into columns
const layoutItems: PaletteItem[] = [
  { type: 'Tab', icon: '⊟', label: 'Tab' },
  { type: 'Section', icon: '═', label: 'Section' },
]

function cloneField(item: PaletteItem): DocField {
  return {
    fieldname: builder.generateFieldname(item.type),
    label: item.label,
    fieldtype: item.type,
  }
}

function addLayoutItem(type: FieldType) {
  if (type === 'Tab') {
    builder.addTab()
  } else if (type === 'Section') {
    // Add section to the current layout — addField appends to end
    builder.addField('Section')
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto p-3 border-r border-border bg-background">
    <p class="text-xs font-semibold text-muted-foreground/70 uppercase tracking-wide mb-3 px-1">Fields</p>

    <!-- Draggable field groups -->
    <div v-for="group in fieldGroups" :key="group.label" class="mb-4">
      <p class="text-xs text-muted-foreground/70 px-1 mb-1">{{ group.label }}</p>
      <draggable
        :model-value="group.items"
        :group="{ name: 'builder-fields', pull: 'clone', put: false }"
        :sort="false"
        item-key="type"
        :clone="cloneField"
        class="flex flex-col gap-0.5"
      >
        <template #item="{ element: item }">
          <div
            class="flex items-center gap-2 px-2 py-1.5 text-sm rounded hover:bg-border transition-colors text-left w-full cursor-grab active:cursor-grabbing"
          >
            <span class="text-base w-5 text-center shrink-0">{{ item.icon }}</span>
            <span class="text-foreground">{{ item.label }}</span>
          </div>
        </template>
      </draggable>
    </div>

    <!-- Layout items (click only) -->
    <div class="mb-4">
      <p class="text-xs text-muted-foreground/70 px-1 mb-1">Структурні</p>
      <div class="flex flex-col gap-0.5">
        <button
          v-for="item in layoutItems"
          :key="item.type"
          type="button"
          class="flex items-center gap-2 px-2 py-1.5 text-sm rounded hover:bg-border transition-colors text-left w-full"
          @click="addLayoutItem(item.type)"
        >
          <span class="text-base w-5 text-center shrink-0">{{ item.icon }}</span>
          <span class="text-foreground">{{ item.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
