<script setup lang="ts">
import type { DocField } from '@/types'

defineProps<{
  field: DocField
  selected: boolean
}>()

const emit = defineEmits<{
  select: []
  remove: []
}>()

const FIELD_ICONS: Record<string, string> = {
  Text: 'T', LongText: '¶', Int: '#', Float: '.1', Check: '✓', Date: '📅',
  Datetime: '🕐', Time: '⏰', Select: '▼', Link: '🔗', Attach: '📎', Image: '🖼',
  RichText: '✍', JSON: '{}', Code: '<>', Color: '🎨', Geolocation: '📍',
  Table: '▦', Signature: '✒', MultiLink: '⛓',
}
</script>

<template>
  <div
    class="group flex items-center gap-2 bg-[--grunt-surface] border rounded-[--grunt-radius-sm] transition-all cursor-pointer text-sm"
    :class="selected
      ? 'border-[--grunt-primary] ring-2 ring-[--grunt-primary]/20'
      : 'border-[--grunt-border] hover:border-[--grunt-border-strong]'"
    @click.stop="emit('select')"
  >
    <!-- Drag handle -->
    <div class="drag-handle px-1.5 py-2 text-[--grunt-text-muted] hover:text-[--grunt-text-secondary] cursor-grab active:cursor-grabbing shrink-0 text-xs">
      ⠿
    </div>

    <!-- Icon + label -->
    <div class="flex-1 py-2 min-w-0 flex items-center gap-1.5">
      <span class="text-xs shrink-0 w-4 text-center">{{ FIELD_ICONS[field.fieldtype] ?? '?' }}</span>
      <span class="font-medium text-[--grunt-text-primary] truncate">{{ field.label || field.fieldname }}</span>
      <span class="text-xs text-[--grunt-text-muted] truncate hidden sm:inline">({{ field.fieldname }})</span>
      <span v-if="field.required" class="text-[--grunt-danger] text-xs">*</span>
    </div>

    <!-- Type badge -->
    <span class="text-[10px] text-[--grunt-text-muted] bg-[--grunt-surface-secondary] px-1.5 py-0.5 rounded shrink-0">
      {{ field.fieldtype }}
    </span>

    <!-- Delete -->
    <button
      type="button"
      class="px-2 py-2 text-[--grunt-text-muted] hover:text-[--grunt-danger] opacity-0 group-hover:opacity-100 transition-all shrink-0"
      @click.stop="emit('remove')"
    >×</button>
  </div>
</template>
