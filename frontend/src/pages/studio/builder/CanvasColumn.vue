<script setup lang="ts">
import { computed } from 'vue'
import draggable from 'vuedraggable'
import type { DocField } from '@/types'
import { useBuilderStore } from '@/stores/builder'
import CanvasFieldCard from './CanvasFieldCard.vue'

const props = defineProps<{
  fields: DocField[]
}>()

const emit = defineEmits<{
  'update:fields': [fields: DocField[]]
}>()

const builder = useBuilderStore()

const localFields = computed({
  get: () => props.fields,
  set: (val: DocField[]) => emit('update:fields', val),
})
</script>

<template>
  <div class="min-h-[60px]">
    <draggable
      v-model="localFields"
      group="builder-fields"
      item-key="fieldname"
      handle=".drag-handle"
      ghost-class="opacity-30"
      class="flex flex-col gap-1.5 min-h-[60px] p-1.5 rounded-[--grunt-radius-sm] border border-dashed border-transparent transition-colors"
      :class="{ 'border-[--grunt-border] bg-[--grunt-surface-secondary]/50': !fields.length }"
    >
      <template #item="{ element: f }">
        <CanvasFieldCard
          :field="f"
          :selected="builder.selectedFieldName === f.fieldname"
          @select="builder.selectField(f.fieldname)"
          @remove="builder.removeField(f.fieldname)"
        />
      </template>

      <template #footer>
        <div
          v-if="!fields.length"
          class="flex items-center justify-center h-10 text-[--grunt-text-muted] text-xs select-none"
        >
          Drop fields here
        </div>
      </template>
    </draggable>
  </div>
</template>
