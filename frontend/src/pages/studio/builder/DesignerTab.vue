<script setup lang="ts">
import { onMounted, watch, ref } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import type { DocType } from '@/types'
import FieldPalette from './FieldPalette.vue'
import BuilderCanvas from './BuilderCanvas.vue'
import PropertiesPanel from './PropertiesPanel.vue'
import IndexHintsBar from './IndexHintsBar.vue'

const props = defineProps<{
  doctype: DocType
  modelValue: Record<string, any>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, any>]
}>()

const builder = useBuilderStore()
const ready = ref(false)

// This tab is unmounted by the surrounding <TabsContent> whenever it isn't the
// active tab, so it re-seeds from the live form model on every visit. While it
// *is* mounted the designer is the only editor touching the model, so a single
// outward mirror (builder.doctype -> modelValue) is enough - no inbound watcher,
// no echo loop.
watch(() => builder.doctype, (newVal) => {
  if (ready.value && newVal) emit('update:modelValue', { ...newVal })
}, { deep: true, flush: 'sync' })

onMounted(() => {
  builder.doctype = { fields: [], ...props.modelValue } as unknown as DocType
  ready.value = true
})
</script>

<template>
  <div class="flex flex-col h-[75vh] min-h-[30rem] overflow-hidden -mx-5 -mb-5 border-t border-border bg-background">
    <IndexHintsBar />
    <div class="flex flex-1 overflow-hidden">
      <div class="w-60 shrink-0 border-r bg-card/50 overflow-y-auto">
        <FieldPalette />
      </div>
      <div class="flex-1 overflow-hidden bg-muted/5 flex flex-col">
        <BuilderCanvas class="flex-1" />
      </div>
      <div class="w-72 shrink-0 border-l bg-card/50 overflow-y-auto">
        <PropertiesPanel />
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.builder-canvas) {
  padding: 1.5rem;
}
</style>
