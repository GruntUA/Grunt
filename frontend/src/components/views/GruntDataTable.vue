<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import type { DocField, DocTypeStatusConfig } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { getListCell } from '@/core/listCellRegistry'
import DefaultListCell from '@/components/fields/Default/ListCell.vue'

const props = defineProps<{
  columns: ListColumn[]
  rows: Record<string, unknown>[]
  fields: DocField[]
  isLoading: boolean
  sortKey: string
  sortOrder: 'asc' | 'desc'
  selectedIds: string[]
  allSelected?: boolean
  statusConfig?: DocTypeStatusConfig | null
  hideHeader?: boolean
  hideBody?: boolean
  activeIndex?: number
}>()

const emit = defineEmits<{
  sort: [key: string]
  select: [id: string]
  selectAll: []
  rowClick: [row: Record<string, unknown>]
  inlineUpdate: [rowId: string, field: string, value: string]
}>()

// ── Selection bridge ───────────────────────────────────────────────────────
const selection = computed({
  get: () => props.allSelected ? props.rows : props.rows.filter(r => props.selectedIds.includes(String(r.id))),
  set: (_val: Record<string, unknown>[]) => {
    // This is tricky because emit select is per-id. 
    // Usually, we'd just want to emit the whole set, but the framework expects individual selects.
    // For now, we'll keep using our manual selection logic but triggered by PrimeVue events
  }
})

function onRowSelect(e: any) {
  emit('select', String(e.data.id))
}

function onRowUnselect(e: any) {
  emit('select', String(e.data.id)) // Our emit just toggles
}

function onSelectAll() {
  emit('selectAll')
}

// ── Inline editing ────────────────────────────────────────────────────────
interface InlineEdit { rowId: string; field: string; value: string }
const inlineEdit = ref<InlineEdit | null>(null)
const inlineInput = ref<HTMLInputElement | null>(null)

const INLINE_SKIP = new Set(['Check', 'Select', 'Date', 'Datetime', 'Image', 'Attach', 'RichText', 'JSON', 'Code', 'Signature', 'Link', 'Rating', 'Icon'])

function isEditing(rowId: string, field: string) {
  return inlineEdit.value?.rowId === rowId && inlineEdit.value?.field === field
}

async function startEdit(row: any, field: string, fieldtype: string) {
  if (INLINE_SKIP.has(fieldtype) || props.fields.find(f => f.fieldname === field)?.read_only) return
  inlineEdit.value = { rowId: String(row.id), field, value: String(row[field] ?? '') }
  await nextTick()
  inlineInput.value?.focus()
}

function commitEdit() {
  if (!inlineEdit.value) return
  emit('inlineUpdate', inlineEdit.value.rowId, inlineEdit.value.field, inlineEdit.value.value)
  inlineEdit.value = null
}

function cancelEdit() {
  inlineEdit.value = null
}

// ── Helpers ────────────────────────────────────────────────────────────────

const fieldMap = computed(() => {
  const m: Record<string, DocField> = {}
  props.fields.forEach(f => { m[f.fieldname] = f })
  return m
})

function getFieldType(key: string): string {
  return fieldMap.value[key]?.fieldtype ?? 'Text'
}

const sortOrderValue = computed(() => props.sortOrder === 'desc' ? -1 : 1)


// Mapping for PT (Pass Through) to match our design system
const pt = {
    root: { class: 'border-0' },
    header: { class: 'hidden' }, // We use custom header usually or none
    thead: { class: props.hideHeader ? 'hidden' : '' },
    headerRow: { class: 'bg-muted/30 backdrop-blur-sm' },
    headerCell: (slotProps: any) => ({ 
        class: [
            'px-6 py-4 text-[10px] font-black uppercase tracking-[0.2em] border-b border-border/40 text-left transition-all duration-200',
            slotProps.context.sorted ? 'text-primary' : 'text-muted-foreground/50 hover:text-foreground/80'
        ]
    }),
    bodyRow: (slotProps: any) => {
        const isActive = props.activeIndex === slotProps.index;
        return {
            class: [
                'transition-all duration-300 cursor-pointer border-b border-border/20 last:border-0 hover:bg-primary/[0.04]',
                { 'bg-primary/[0.05] hover:bg-primary/[0.08]': slotProps.selected },
                { 'ring-inset ring-2 ring-primary/60 scale-[1.002] z-20 relative shadow-lg bg-background': isActive }
            ]
        }
    },
    bodyCell: { class: 'px-6 py-4 text-sm border-b border-border/10' },
    loadingOverlay: { class: 'bg-card/50 backdrop-blur-sm' }
}
</script>

<template>
  <DataTable
    :value="rows"
    :loading="isLoading && !rows.length"
    data-key="id"
    :selection="selection"
    @row-select="onRowSelect"
    @row-unselect="onRowUnselect"
    @select-all-change="onSelectAll"
    @row-click="(e: { data: any }) => emit('rowClick', e.data)"
    :sort-field="sortKey"
    :sort-order="sortOrderValue"
    @sort="(e: any) => emit('sort', String(e.sortField))"
    responsive-layout="scroll"
    :pt="pt"
    class="w-full text-sm"
  >
    <!-- Skeleton Loading -->
    <template #loading>
       <div class="flex flex-col gap-2">
           <Skeleton v-for="i in 8" :key="i" height="3rem" />
       </div>
    </template>

    <!-- Selection Column -->
    <Column header-style="width: 3rem" class="relative">
        <template #header>
            <div class="flex items-center justify-center w-full">
                <Checkbox binary 
                  :model-value="props.allSelected || (props.rows.length > 0 && props.selectedIds.length === props.rows.length)" 
                  @change="emit('selectAll')" />
            </div>
        </template>
        <template #body="slotProps">
            <div v-if="props.selectedIds.includes(String(slotProps.data.id))"
              class="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-r-full pointer-events-none" />
            <Checkbox binary 
              :model-value="props.selectedIds.includes(String(slotProps.data.id))" 
              @change="emit('select', String(slotProps.data.id))" />
        </template>
    </Column>

    <!-- Data Columns -->
    <Column v-for="(col, ci) in columns" :key="col.key"
      :field="col.key"
      :header="col.label"
      :sortable="col.sortable"
      class="max-w-xs wrap-break-word"
    >
      <template #body="slotProps">
        <div @dblclick.stop="ci > 0 && startEdit(slotProps.data, col.key, getFieldType(col.key))">
          <!-- Inline edit input -->
          <template v-if="isEditing(String(slotProps.data.id), col.key)">
            <input ref="inlineInput" v-model="inlineEdit!.value"
              class="w-full rounded-md border border-primary px-2 py-1 text-sm bg-background shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/20 transition-shadow"
              @blur="commitEdit" @keydown.enter.prevent="commitEdit" @keydown.escape.prevent="cancelEdit"
              @click.stop />
          </template>

          <!-- Field-type cell renderer (registry) -->
          <div v-else
            :class="{ 'font-semibold text-primary hover:underline': ci === 0 && !['Image', 'Attach', 'Check'].includes(getFieldType(col.key)) }">
            <component :is="getListCell(getFieldType(col.key)) ?? DefaultListCell" :value="slotProps.data[col.key]" :row="slotProps.data"
              :field="fieldMap[col.key] ?? { fieldname: col.key, fieldtype: 'Data', label: col.label }"
              :status-config="statusConfig" />
          </div>
        </div>
      </template>
    </Column>

    <!-- Empty state -->
    <template #empty>
      <div v-if="!isLoading" class="px-3 py-16 text-center">
        <div class="flex flex-col items-center gap-2">
          <i class="pi pi-file-excel text-muted-foreground/40 text-4xl" />
          <p class="text-sm text-muted-foreground">Записів не знайдено</p>
        </div>
      </div>
    </template>
  </DataTable>
</template>

<style scoped>
:deep(.p-datatable-header-cell),
:deep(.p-datatable-column-sortable),
:deep(.p-datatable-column-sorted),
:deep(.p-datatable-header-cell.p-datatable-column-sorted),
:deep(.p-datatable-header-cell.p-datatable-column-sorted:hover) {
    background: transparent !important;
    background-color: transparent !important;
    box-shadow: none !important;
}
</style>
