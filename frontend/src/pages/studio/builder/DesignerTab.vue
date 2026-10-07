<script setup lang="ts">
import { computed, onMounted, watch, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocalStorage } from '@vueuse/core'
import { LayoutTemplate, Table2 } from '@lucide/vue'
import { useBuilderStore } from '@/stores/builder'
import type { DocType } from '@/types'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import FieldRenderer from '@/core/renderer/FieldRenderer.vue'
import FieldPalette from './FieldPalette.vue'
import BuilderCanvas from './BuilderCanvas.vue'
import PropertiesPanel from './PropertiesPanel.vue'
import IndexHintsBar from './IndexHintsBar.vue'

type Mode = 'canvas' | 'table'

const props = defineProps<{
  doctype: DocType
  modelValue: Record<string, any>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, any>]
}>()

const { t } = useI18n()
const builder = useBuilderStore()
const ready = ref(false)
const mode = useLocalStorage<Mode>('grunt.builder.mode', 'canvas')

// The same `fields` Table field the form would render - edited as plain rows.
const fieldsTable = computed(() => props.doctype.fields.find((f) => f.fieldname === 'fields'))

// This tab is unmounted by the surrounding <TabsContent> whenever it isn't the
// active tab, so it re-seeds from the live form model on every visit. While the
// canvas is shown it is the only editor touching the model, so a single
// outward mirror (builder.doctype -> modelValue) is enough - no inbound watcher,
// no echo loop. The table edits the model directly; switching back re-seeds.
watch(() => builder.doctype, (newVal) => {
  if (ready.value && mode.value === 'canvas' && newVal) emit('update:modelValue', { ...newVal })
}, { deep: true, flush: 'sync' })

function seed() {
  ready.value = false
  builder.doctype = { fields: [], ...props.modelValue } as unknown as DocType
  ready.value = true
}

function setMode(value: unknown) {
  if (value !== 'canvas' && value !== 'table') return
  mode.value = value
  if (value === 'canvas') seed()
}

onMounted(seed)
</script>

<template>
  <div class="flex flex-col h-[75vh] min-h-[30rem] overflow-hidden -mx-5 -mb-5 border-t border-border bg-background">
    <IndexHintsBar v-if="mode === 'canvas'" />
    <div class="flex items-center justify-end border-b px-3 py-1.5">
      <ToggleGroup type="single" variant="outline" size="sm" :model-value="mode" @update:model-value="setMode">
        <ToggleGroupItem value="canvas" class="px-2.5">
          <LayoutTemplate /> {{ t('Canvas') }}
        </ToggleGroupItem>
        <ToggleGroupItem value="table" class="px-2.5">
          <Table2 /> {{ t('Table') }}
        </ToggleGroupItem>
      </ToggleGroup>
    </div>
    <div v-if="mode === 'table'" class="flex-1 overflow-y-auto p-5">
      <FieldRenderer
        v-if="fieldsTable"
        :field="fieldsTable"
        :model-value="modelValue.fields"
        :doc-values="modelValue"
        @update:model-value="emit('update:modelValue', { ...modelValue, fields: $event })"
      />
    </div>
    <div v-else class="flex flex-1 overflow-hidden">
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
