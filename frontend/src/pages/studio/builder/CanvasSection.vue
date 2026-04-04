<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { DocField } from '@/types'
import { useBuilderStore } from '@/stores/builder'
import type { LayoutSection } from '@/core/composables/useFormLayout'
import CanvasColumn from './CanvasColumn.vue'

const props = defineProps<{
  section: LayoutSection
}>()

const emit = defineEmits<{
  'update:section': [section: LayoutSection]
  delete: []
}>()

const builder = useBuilderStore()
const isEditingLabel = ref(false)
const editLabel = ref('')

// Local mutable copy of columns — allows both drag events (remove + add)
// to accumulate before we emit a single consistent update.
const localColumns = ref<DocField[][]>([])

watch(
  () => props.section.columns,
  (cols) => { localColumns.value = cols.map((c) => [...c]) },
  { immediate: true, deep: false },
)

function startEditLabel() {
  editLabel.value = props.section.label
  isEditingLabel.value = true
}

function finishEditLabel() {
  isEditingLabel.value = false
  if (props.section._field) {
    builder.updateField(props.section._fieldname, { label: editLabel.value })
  }
}

function setColumns(count: number) {
  builder.setSectionColumns(props.section._fieldname, count)
}

let _pendingEmit = false
function updateColumnFields(colIndex: number, newFields: DocField[]) {
  localColumns.value[colIndex] = newFields
  if (!_pendingEmit) {
    _pendingEmit = true
    nextTick(() => {
      emit('update:section', { ...props.section, columns: localColumns.value })
      _pendingEmit = false
    })
  }
}

function toggleCollapsible() {
  if (props.section._field) {
    builder.updateField(props.section._fieldname, { collapsible: !props.section.collapsible })
  }
}

function selectSection() {
  if (props.section._field) {
    builder.selectField(props.section._fieldname)
  }
}
</script>

<template>
  <div
    class="border border-border rounded-md bg-card overflow-hidden"
    :class="builder.selectedFieldName === section._fieldname ? 'ring-2 ring-primary/20' : ''"
  >
    <!-- Section header -->
    <div
      class="flex items-center gap-2 px-3 py-2 bg-background border-b border-border cursor-pointer select-none"
      @click="selectSection"
    >
      <!-- Collapsible indicator -->
      <button
        v-if="section._field"
        type="button"
        class="text-xs text-muted-foreground/70 hover:text-muted-foreground w-4 shrink-0"
        :title="section.collapsible ? 'Collapsible' : 'Not collapsible'"
        @click.stop="toggleCollapsible"
      >
        {{ section.collapsible ? '▼' : '━' }}
      </button>

      <!-- Label (editable) -->
      <template v-if="isEditingLabel">
        <input
          v-model="editLabel"
          type="text"
          class="flex-1 text-xs font-semibold uppercase tracking-wide bg-transparent border-b border-primary outline-none text-foreground px-0 py-0"
          @blur="finishEditLabel"
          @keydown.enter="finishEditLabel"
          @keydown.escape="isEditingLabel = false"
          @click.stop
          autofocus
        />
      </template>
      <template v-else>
        <span
          class="flex-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground truncate"
          :class="{ 'text-muted-foreground/70 italic': !section.label }"
          @dblclick.stop="startEditLabel"
        >
          {{ section.label || 'Section (double-click to rename)' }}
        </span>
      </template>

      <!-- Column count buttons -->
      <div class="flex items-center gap-0.5 shrink-0">
        <button
          v-for="n in 4"
          :key="n"
          type="button"
          class="w-5 h-5 text-[10px] rounded flex items-center justify-center transition-colors"
          :class="section.columns.length === n
            ? 'bg-primary text-white'
            : 'text-muted-foreground/70 hover:bg-border'"
          :title="`${n} column${n > 1 ? 's' : ''}`"
          @click.stop="setColumns(n)"
        >{{ n }}</button>
      </div>

      <!-- Delete section -->
      <button
        v-if="section._field"
        type="button"
        class="text-muted-foreground/70 hover:text-destructive text-xs shrink-0 px-1"
        title="Delete section"
        @click.stop="emit('delete')"
      >×</button>
    </div>

    <!-- Columns grid -->
    <div
      class="p-2 gap-2"
      :style="{ display: 'grid', gridTemplateColumns: `repeat(${section.columns.length}, 1fr)` }"
    >
      <CanvasColumn
        v-for="(col, ci) in section.columns"
        :key="ci"
        :fields="col"
        @update:fields="updateColumnFields(ci, $event)"
      />
    </div>
  </div>
</template>
