<script setup lang="ts">
import { computed } from 'vue'
import draggable from 'vuedraggable'
import { useBuilderStore } from '@/stores/builder'
import type { DocField } from '@/types'

const builder = useBuilderStore()

const fields = computed({
  get: () => builder.doctype?.fields ?? [],
  set: (val: DocField[]) => {
    if (builder.doctype) {
      builder.doctype.fields = val
      builder.isDirty = true
    }
  },
})

const FIELD_ICONS: Record<string, string> = {
  Text: 'T', LongText: '¶', Int: '1', Float: '.1', Check: '✓', Date: '📅',
  Datetime: '🕐', Time: '⏰', Select: '▼', Link: '🔗', Attach: '📎', Image: '🖼',
  RichText: '✍', JSON: '{}', Code: '<>', Color: '🎨', Geolocation: '📍',
  Section: '═', Column: '║', Tab: '⊟', Table: '▦', Signature: '✒',
}

function isLayoutField(f: DocField) {
  return ['Section', 'Column', 'Tab'].includes(f.fieldtype)
}
</script>

<template>
  <div class="h-full overflow-y-auto p-4">
    <draggable
      v-model="fields"
      item-key="fieldname"
      handle=".drag-handle"
      ghost-class="opacity-30"
      class="flex flex-col gap-2 min-h-32"
    >
      <template #item="{ element: f, index: i }">
        <div
          class="group flex items-center gap-2 bg-[--grunt-surface] border rounded-[--grunt-radius-md] transition-all cursor-pointer"
          :class="builder.selectedFieldIndex === i
            ? 'border-[--grunt-primary] ring-2 ring-[--grunt-primary]/20'
            : 'border-[--grunt-border] hover:border-[--grunt-border-strong]'"
          @click="builder.selectField(i)"
        >
          <!-- Drag handle -->
          <div class="drag-handle px-2 py-3 text-[--grunt-text-muted] hover:text-[--grunt-text-secondary] cursor-grab active:cursor-grabbing shrink-0">
            ⠿
          </div>

          <!-- Content -->
          <div class="flex-1 py-2.5 min-w-0">
            <!-- Section / Tab as header -->
            <template v-if="isLayoutField(f)">
              <div class="flex items-center gap-2">
                <span class="text-xs font-bold text-[--grunt-text-muted] uppercase">{{ f.fieldtype }}</span>
                <span class="text-sm font-medium text-[--grunt-text-primary]">{{ f.label || '—' }}</span>
              </div>
            </template>
            <template v-else>
              <div class="flex items-center gap-2">
                <span class="text-sm shrink-0">{{ FIELD_ICONS[f.fieldtype] ?? '?' }}</span>
                <span class="text-sm font-medium text-[--grunt-text-primary] truncate">{{ f.label || f.fieldname }}</span>
                <span class="text-xs text-[--grunt-text-muted] truncate">({{ f.fieldname }})</span>
                <span v-if="f.required" class="text-xs text-[--grunt-danger]">*</span>
              </div>
            </template>
          </div>

          <!-- Delete -->
          <button
            type="button"
            class="px-3 py-3 text-[--grunt-text-muted] hover:text-[--grunt-danger] opacity-0 group-hover:opacity-100 transition-all shrink-0"
            @click.stop="builder.removeField(i)"
          >×</button>
        </div>
      </template>

      <template #footer>
        <div
          v-if="!fields.length"
          class="flex items-center justify-center h-32 border-2 border-dashed border-[--grunt-border] rounded-[--grunt-radius-lg] text-[--grunt-text-muted] text-sm"
        >
          Перетягни поле з палітри або клікни на тип
        </div>
      </template>
    </draggable>
  </div>
</template>
