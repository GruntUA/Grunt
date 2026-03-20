<script setup lang="ts">
import { useBuilderStore } from '@/stores/builder'
import type { FieldType } from '@/types'

const builder = useBuilderStore()

const groups: { label: string; items: { type: FieldType; icon: string; label: string }[] }[] = [
  {
    label: 'Базові',
    items: [
      { type: 'Text', icon: 'T', label: 'Text' },
      { type: 'LongText', icon: '¶', label: 'Long Text' },
      { type: 'Int', icon: '1', label: 'Integer' },
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
    label: 'Структурні',
    items: [
      { type: 'Section', icon: '═', label: 'Section' },
      { type: 'Column', icon: '║', label: 'Column' },
      { type: 'Tab', icon: '⊟', label: 'Tab' },
      { type: 'Table', icon: '▦', label: 'Table' },
    ],
  },
]
</script>

<template>
  <div class="h-full overflow-y-auto p-3 border-r border-[--grunt-border] bg-[--grunt-surface-secondary]">
    <p class="text-xs font-semibold text-[--grunt-text-muted] uppercase tracking-wide mb-3 px-1">Поля</p>
    <div v-for="group in groups" :key="group.label" class="mb-4">
      <p class="text-xs text-[--grunt-text-muted] px-1 mb-1">{{ group.label }}</p>
      <div class="flex flex-col gap-0.5">
        <button
          v-for="item in group.items"
          :key="item.type"
          type="button"
          class="flex items-center gap-2 px-2 py-1.5 text-sm rounded hover:bg-[--grunt-border] transition-colors text-left w-full"
          @click="builder.addField(item.type)"
        >
          <span class="text-base w-5 text-center shrink-0">{{ item.icon }}</span>
          <span class="text-[--grunt-text-primary]">{{ item.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
