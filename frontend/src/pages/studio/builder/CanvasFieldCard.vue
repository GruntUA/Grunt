<script setup lang="ts">
import { defineAsyncComponent, shallowRef, watchEffect } from 'vue'
import type { Component } from 'vue'
import type { DocField } from '@/types'
import { getFieldDef, FallbackFieldLoader } from '@/core/fieldRegistry'

const props = defineProps<{
  field: DocField
  selected: boolean
}>()

const emit = defineEmits<{
  select: []
  remove: []
}>()

// Recreate async component only when fieldtype changes
const previewComponent = shallowRef<Component | null>(null)
watchEffect(() => {
  const def = getFieldDef(props.field.fieldtype)
  const loader = def?.designerPreview ?? def?.component ?? FallbackFieldLoader
  previewComponent.value = defineAsyncComponent({ loader, timeout: 5000 })
})
</script>

<template>
  <div
    class="group bg-card border rounded-md transition-all cursor-pointer overflow-hidden"
    :class="selected
      ? 'border-primary ring-2 ring-primary/20 shadow-sm'
      : 'border-border hover:border-border/80 hover:shadow-sm'"
    @click.stop="emit('select')"
  >
    <!-- ── Header row ── -->
    <div class="flex items-center gap-1.5 px-2 py-1.5 border-b border-border/50 bg-muted/30">
      <span class="drag-handle text-muted-foreground/50 hover:text-muted-foreground cursor-grab active:cursor-grabbing text-xs shrink-0 select-none">⠿</span>

      <span class="font-medium text-foreground text-xs truncate flex-1">
        {{ field.label || field.fieldname }}
        <span v-if="field.required" class="text-destructive ml-0.5">*</span>
      </span>

      <span v-if="field.formula"
        class="text-[10px] font-mono text-amber-600 bg-amber-50 border border-amber-200 px-1 py-px rounded shrink-0">ƒx</span>
      <span v-if="field.aggregate_function"
        class="text-[10px] font-mono text-blue-600 bg-blue-50 border border-blue-200 px-1 py-px rounded shrink-0">∑</span>

      <span class="text-[10px] text-muted-foreground/60 shrink-0">{{ field.fieldtype }}</span>

      <button
        type="button"
        class="text-muted-foreground/40 hover:text-destructive opacity-0 group-hover:opacity-100 transition-all shrink-0 leading-none px-0.5"
        @click.stop="emit('remove')"
      >×</button>
    </div>

    <!-- ── Field preview ── -->
    <div class="px-3 pt-2 pb-2.5 pointer-events-none select-none">
      <component
        :is="previewComponent"
        :field="field"
        :model-value="field.default"
        :disabled="true"
      />
      <p class="mt-1.5 text-[10px] text-muted-foreground/40 font-mono">{{ field.fieldname }}</p>
    </div>
  </div>
</template>
