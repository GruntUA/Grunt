<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import Checkbox from 'primevue/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  FileX,
} from '@lucide/vue'
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

// ── Inline editing ────────────────────────────────────────────────────────
interface InlineEdit { rowId: string; field: string; value: string }
const inlineEdit = ref<InlineEdit | null>(null)
const inlineInput = ref<HTMLInputElement | null>(null)

const INLINE_SKIP = new Set(['Check', 'Select', 'Date', 'Datetime', 'Image', 'Attach', 'RichText', 'JSON', 'Code', 'Signature', 'Link', 'Rating', 'Icon'])

function canInlineEdit(fieldtype: string): boolean {
  return !INLINE_SKIP.has(fieldtype)
}

async function startEdit(row: Record<string, unknown>, field: string, fieldtype: string) {
  if (!canInlineEdit(fieldtype)) return
  inlineEdit.value = { rowId: String(row.id), field, value: String(row[field] ?? '') }
  await nextTick()
  inlineInput.value?.focus()
  inlineInput.value?.select()
}

function commitEdit() {
  if (!inlineEdit.value) return
  emit('inlineUpdate', inlineEdit.value.rowId, inlineEdit.value.field, inlineEdit.value.value)
  inlineEdit.value = null
}

function cancelEdit() {
  inlineEdit.value = null
}

function isEditing(rowId: string, field: string): boolean {
  return inlineEdit.value?.rowId === rowId && inlineEdit.value?.field === field
}

const fieldMap = computed(() => {
  const m: Record<string, DocField> = {}
  for (const f of props.fields) m[f.fieldname] = f
  return m
})

function getFieldType(key: string): string {
  return fieldMap.value[key]?.fieldtype ?? 'Text'
}


function isSelected(id: string) {
  return props.allSelected || props.selectedIds.includes(id)
}
</script>

<template>
  <!-- Skeleton loading (first load — no rows yet) -->
  <div v-if="isLoading && !rows.length" class="overflow-hidden rounded-md border">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-border bg-muted/50">
          <th class="w-10 px-3 py-3">
            <Skeleton class="h-4 w-4" />
          </th>
          <th v-for="col in columns" :key="col.key" class="px-3 py-3">
            <Skeleton class="h-3 w-20" />
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="i in 8" :key="i" class="border-b border-border last:border-0">
          <td class="px-3 py-3">
            <Skeleton class="h-4 w-4" />
          </td>
          <td v-for="col in columns" :key="col.key" class="px-3 py-3">
            <Skeleton class="h-4" :class="col === columns[0] ? 'w-32' : 'w-20'" />
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- Table -->
  <div v-else class="overflow-hidden rounded-xl border border-border/60 bg-card shadow-sm">
    <table class="w-full text-sm">
      <thead v-if="!hideHeader">
        <tr class="border-b border-border/40 bg-muted/40 backdrop-blur-sm">
          <th class="w-10 px-4 py-3.5">
            <Checkbox binary :model-value="allSelected || (rows.length > 0 && selectedIds.length === rows.length)"
              @update:model-value="emit('selectAll')" class="bg-background" />
          </th>
          <th v-for="col in columns" :key="col.key"
            class="text-left px-4 py-3.5 text-[11px] font-bold uppercase tracking-[0.1em] text-muted-foreground/80 select-none transition-colors"
            :class="{ 'cursor-pointer hover:text-foreground group/th': col.sortable }"
            @click="col.sortable && emit('sort', col.key)">
            <span class="inline-flex items-center gap-1">
              {{ col.label }}
              <ArrowUp v-if="sortKey === col.key && sortOrder === 'asc'" class="size-3.5 text-primary" />
              <ArrowDown v-else-if="sortKey === col.key && sortOrder === 'desc'" class="size-3.5 text-primary" />
              <ArrowUpDown v-else-if="col.sortable"
                class="size-3.5 opacity-0 group-hover/th:opacity-40 transition-opacity" />
            </span>
          </th>
        </tr>
      </thead>
      <tbody v-if="!hideBody">
        <tr v-for="(row, index) in rows" :key="String(row.id)"
          class="border-b border-border/30 last:border-0 hover:bg-muted/40 cursor-pointer transition-all duration-200 group relative"
          :class="[
            isSelected(String(row.id)) ? 'bg-primary/[0.03] hover:bg-primary/[0.05]' : '',
            activeIndex === index ? 'bg-muted/80 ring-inset ring-1 ring-primary/30 z-10' : ''
          ]">

          <td class="relative px-4 py-3" @click.stop>
            <div v-if="isSelected(String(row.id))"
              class="absolute left-0 top-0 bottom-0 w-0.5 bg-primary rounded-r-full pointer-events-none" />
            <Checkbox binary :model-value="isSelected(String(row.id))" @update:model-value="emit('select', String(row.id))"
              class="transition-transform duration-200" :class="{ 'scale-110': isSelected(String(row.id)) }" />
          </td>
          <td v-for="(col, ci) in columns" :key="col.key" class="px-4 py-3 text-[13px] max-w-xs break-words"
            @click="!isEditing(String(row.id), col.key) && emit('rowClick', row)"
            @dblclick.stop="ci > 0 && startEdit(row, col.key, getFieldType(col.key))">
            <!-- Inline edit input -->
            <template v-if="isEditing(String(row.id), col.key)">
              <input ref="inlineInput" v-model="inlineEdit!.value"
                class="w-full rounded-md border border-primary px-2 py-1 text-sm bg-background shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/20 transition-shadow"
                @blur="commitEdit" @keydown.enter.prevent="commitEdit" @keydown.escape.prevent="cancelEdit"
                @click.stop />
            </template>

            <!-- Field-type cell renderer (registry) -->
            <div v-else
              :class="{ 'font-semibold text-primary hover:underline': ci === 0 && !['Image', 'Attach', 'Check'].includes(getFieldType(col.key)) }">
              <component :is="getListCell(getFieldType(col.key)) ?? DefaultListCell" :value="row[col.key]" :row="row"
                :field="fieldMap[col.key] ?? { fieldname: col.key, fieldtype: 'Data', label: col.label }"
                :status-config="statusConfig" />
            </div>
          </td>
        </tr>
        <!-- Empty state -->
        <tr v-if="!rows.length && !isLoading">
          <td :colspan="columns.length + 1" class="px-3 py-16 text-center">
            <div class="flex flex-col items-center gap-2">
              <FileX class="size-10 text-muted-foreground/40" />
              <p class="text-sm text-muted-foreground">Записів не знайдено</p>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
