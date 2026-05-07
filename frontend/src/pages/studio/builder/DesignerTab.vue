<script setup lang="ts">
import { onMounted, watch, ref } from 'vue'
import { useBuilderStore } from '@/stores/builder'
import type { DocType } from '@/types'
import FieldPalette from './FieldPalette.vue'
import BuilderCanvas from './BuilderCanvas.vue'
import PropertiesPanel from './PropertiesPanel.vue'

const props = defineProps<{
  doctype: DocType
  modelValue: Record<string, any>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, any>]
}>()

const builder = useBuilderStore()
const isInitializing = ref(true)

// Sync modelValue -> builder.doctype
watch(() => props.modelValue, (newVal) => {
  if (!builder.isSaving && newVal && !isInitializing.value) {
    builder.doctype = { fields: [], ...newVal } as unknown as DocType
  }
}, { deep: true })

// Sync builder.doctype -> modelValue
watch(() => builder.doctype, (newVal) => {
  if (newVal && !isInitializing.value) {
    emit('update:modelValue', { ...newVal })
  }
}, { deep: true })

onMounted(async () => {
  console.log('DesignerTab initializing with:', props.modelValue?.name)
  // Initialize builder state with current document
  builder.doctype = { fields: [], ...props.modelValue } as unknown as DocType
  builder.isNew = !props.modelValue.name
  builder.isDirty = false
  isInitializing.value = false
})
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-350px)] min-h-[600px] overflow-hidden border rounded-lg bg-background shadow-inner">
    <div v-if="isInitializing" class="flex flex-1 items-center justify-center p-8">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      <span class="ml-2">Завантаження конструктора...</span>
    </div>
    <div v-else class="flex flex-1 overflow-hidden">
      <div class="w-60 shrink-0 border-r bg-card/50 overflow-y-auto">
        <FieldPalette />
      </div>
      <div class="flex-1 overflow-hidden bg-muted/5 flex flex-col relative">
        <div class="absolute top-0 right-0 z-10 px-2 py-1 text-[10px] text-blue-500 font-mono opacity-50">
          DESIGNER TAB ACTIVE
        </div>
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
