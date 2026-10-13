<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, watch, nextTick } from 'vue'
import type { DocField } from '@/types'
import { useBuilderStore } from '@/stores/builder'
import type { LayoutSection } from '@/core/composables/useFormLayout'
import { ChevronDown, GripVertical, Minus, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import CanvasColumn from './CanvasColumn.vue'

const { t } = useI18n()

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

// Local mutable copy of columns - allows both drag events (remove + add)
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
  const label = editLabel.value
  if (!label.trim()) return
  if (props.section._field) {
    builder.updateField(props.section._fieldname, { label })
  } else {
    // Promote implicit section to explicit, then set its label
    const newFieldname = builder.promoteImplicitSection(props.section._fieldname)
    builder.updateField(newFieldname, { label })
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
      <!-- Drag handle -->
      <GripVertical
        class="section-drag-handle size-4 shrink-0 text-muted-foreground/50 hover:text-muted-foreground cursor-grab active:cursor-grabbing"
        role="img"
        :aria-label="t('Drag section')"
        @click.stop
      />

      <!-- Collapsible indicator -->
      <Button
        v-if="section._field"
        variant="ghost" size="icon-xs" class="text-muted-foreground"
        :aria-label="section.collapsible ? t('Collapsible') : t('Not collapsible')"
        @click.stop="toggleCollapsible"
      >
        <ChevronDown v-if="section.collapsible" />
        <Minus v-else />
      </Button>

      <!-- Label (editable) -->
      <template v-if="isEditingLabel">
        <Input
          v-model="editLabel"
          class="h-7 flex-1"
          @blur="finishEditLabel"
          @keydown.enter="finishEditLabel"
          @keydown.escape="isEditingLabel = false"
          @click.stop
          autofocus
        />
      </template>
      <template v-else>
        <span
          class="flex-1 font-semibold tracking-wide text-muted-foreground truncate"
          :class="{ 'text-muted-foreground/70 italic': !section.label }"
          @dblclick.stop="startEditLabel"
        >
          {{ section.label || t('Section (double-click to rename)') }}
        </span>
      </template>

      <!-- Column count buttons -->
      <ToggleGroup
        type="single" size="sm" class="shrink-0"
        :model-value="String(section.columns.length)"
        :aria-label="t('Columns')"
        @update:model-value="(v) => v && setColumns(Number(v))"
        @click.stop
      >
        <ToggleGroupItem v-for="n in 4" :key="n" :value="String(n)" class="px-2">{{ n }}</ToggleGroupItem>
      </ToggleGroup>

      <!-- Delete section -->
      <Button
        v-if="section._field"
        variant="ghost" size="icon-xs" class="text-muted-foreground hover:text-destructive"
        :aria-label="t('Delete section')"
        @click.stop="emit('delete')"
      >
        <X />
      </Button>
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
