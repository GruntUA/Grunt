<script setup lang="ts">
import { computed, inject, type Ref } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
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
const isDraggingField = inject<Ref<boolean>>('fieldDragging')

const localFields = computed({
  get: () => props.fields,
  set: (val: DocField[]) => emit('update:fields', val),
})

function onDragStart() {
  if (isDraggingField) isDraggingField.value = true
}

function onDragEnd() {
  if (isDraggingField) isDraggingField.value = false
}
</script>

<template>
  <div class="min-h-[60px] relative">
    <VueDraggable
      v-model="localFields"
      group="builder-fields"
      handle=".drag-handle"
      ghost-class="opacity-30"
      class="flex flex-col gap-1.5 min-h-[60px] p-1.5 rounded-sm border border-dashed border-transparent transition-colors"
      :class="{ 'border-border bg-background/50': !fields.length }"
      @start="onDragStart"
      @end="onDragEnd"
    >
      <CanvasFieldCard
        v-for="f in localFields"
        :key="f.fieldname"
        :field="f"
        :selected="builder.selectedFieldName === f.fieldname"
        @select="builder.selectField(f.fieldname)"
        @remove="builder.removeField(f.fieldname)"
      />
    </VueDraggable>

    <div
      v-if="!fields.length"
      class="pointer-events-none absolute inset-0 flex items-center justify-center text-muted-foreground/70 select-none"
    >
      Drop fields here
    </div>
  </div>
</template>
