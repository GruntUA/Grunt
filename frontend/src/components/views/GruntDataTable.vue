<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import { FileSpreadsheet, ChevronUp, ChevronDown, ArrowUpDown } from '@lucide/vue'
import type { DocField, DocTypeStatusConfig } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { getListCell } from '@/core/listCellRegistry'
import DefaultListCell from '@/components/fields/Default/ListCell.vue'

const props = defineProps<{
  columns: ListColumn[]
  rows: Record<string, unknown>[]
  fields: DocField[]
  rowLinkBase?: string
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

function getRowDocId(row: Record<string, unknown>): string | null {
  const raw = row.id ?? row.name
  if (raw === null || raw === undefined) return null
  const normalized = String(raw)
  return normalized.length > 0 ? normalized : null
}

// ── Inline editing ────────────────────────────────────────────────────────
interface InlineEdit { rowId: string; field: string; value: string }
const inlineEdit = ref<InlineEdit | null>(null)
const inlineInput = ref<{ focus: () => void } | null>(null)

const INLINE_SKIP = new Set(['Check', 'Select', 'Date', 'Datetime', 'Image', 'Attach', 'RichText', 'JSON', 'Code', 'Signature', 'Link', 'Rating', 'Icon'])

function isEditing(rowId: string, field: string) {
  return inlineEdit.value?.rowId === rowId && inlineEdit.value?.field === field
}

async function startEdit(row: any, field: string, fieldtype: string) {
  if (INLINE_SKIP.has(fieldtype) || props.fields.find(f => f.fieldname === field)?.read_only) return
  inlineEdit.value = { rowId: String(row.id ?? row.name ?? ''), field, value: String(row[field] ?? '') }
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

function rowHref(row: Record<string, unknown>): string | null {
  if (!props.rowLinkBase) return null
  const id = getRowDocId(row)
  if (!id) return null
  return `${props.rowLinkBase}/${encodeURIComponent(id)}`
}

function onRowAnchorClick(event: MouseEvent, row: Record<string, unknown>) {
  if (event.button !== 0) return
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  emit('rowClick', row)
}

function isAllSelected(): boolean {
  return !!(props.allSelected || (props.rows.length > 0 && props.selectedIds.length === props.rows.length))
}
</script>

<template>
  <Table class="w-full text-sm">
    <TableHeader v-if="!hideHeader" class="bg-muted/30">
      <TableRow class="hover:bg-transparent border-0">
        <TableHead style="width: 3rem" class="px-3 py-2.5 border-b border-border/40">
          <div class="flex items-center justify-center w-full">
            <Checkbox :model-value="isAllSelected()" @update:model-value="emit('selectAll')" />
          </div>
        </TableHead>
        <TableHead
          v-for="col in columns" :key="col.key"
          class="px-3 py-2.5 text-xs font-semibold uppercase tracking-widest border-b border-border/40 text-left transition-colors"
          :class="sortKey === col.key ? 'text-foreground' : 'text-muted-foreground hover:text-foreground/80'"
          :role="col.sortable ? 'button' : undefined"
          @click="col.sortable && emit('sort', col.key)"
        >
          <span class="inline-flex items-center gap-1" :class="col.sortable && 'cursor-pointer select-none'">
            {{ col.label }}
            <template v-if="col.sortable">
              <ChevronUp v-if="sortKey === col.key && sortOrder === 'asc'" class="size-3" />
              <ChevronDown v-else-if="sortKey === col.key" class="size-3" />
              <ArrowUpDown v-else class="size-3 opacity-40" />
            </template>
          </span>
        </TableHead>
      </TableRow>
    </TableHeader>

    <TableBody v-if="!hideBody">
      <!-- Skeleton loading -->
      <template v-if="isLoading && !rows.length">
        <TableRow v-for="i in 8" :key="i" class="border-b border-border/20 last:border-0">
          <TableCell :colspan="columns.length + 1" class="px-3 py-2.5">
            <Skeleton class="h-[1.5rem]" />
          </TableCell>
        </TableRow>
      </template>

      <!-- Empty state -->
      <TableRow v-else-if="!isLoading && !rows.length">
        <TableCell :colspan="columns.length + 1" class="px-3 py-16 text-center border-0">
          <div class="flex flex-col items-center gap-2">
            <FileSpreadsheet class="text-muted-foreground/40 text-4xl" />
            <p class="text-sm text-muted-foreground">Записів не знайдено</p>
          </div>
        </TableCell>
      </TableRow>

      <!-- Rows -->
      <TableRow
        v-for="(row, ri) in rows" :key="getRowDocId(row) ?? ri"
        class="cursor-pointer border-b border-border/20 last:border-0 transition-colors hover:bg-primary/5"
        :class="[
          { 'bg-primary/5 hover:bg-primary/10': selectedIds.includes(getRowDocId(row) ?? '') },
          { 'ring-inset ring-2 ring-primary/60 z-20 relative bg-background': activeIndex === ri },
        ]"
        @click="emit('rowClick', row)"
      >
        <TableCell class="relative px-3 py-2.5 text-sm border-b border-border/10">
          <div v-if="selectedIds.includes(getRowDocId(row) ?? '')"
            class="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-r-full pointer-events-none" />
          <Checkbox
            :model-value="selectedIds.includes(getRowDocId(row) ?? '')"
            @update:model-value="() => { const docId = getRowDocId(row); if (docId) emit('select', docId) }"
            @click.stop
          />
        </TableCell>

        <TableCell v-for="(col, ci) in columns" :key="col.key" class="px-3 py-2.5 text-sm border-b border-border/10 max-w-xs whitespace-normal wrap-break-word">
          <div @dblclick.stop="ci > 0 && startEdit(row, col.key, getFieldType(col.key))">
            <!-- Inline edit input -->
            <template v-if="isEditing(getRowDocId(row) ?? '', col.key)">
              <Input ref="inlineInput" v-model="inlineEdit!.value" class="h-8 border-primary"
                @blur="commitEdit" @keydown.enter.prevent="commitEdit" @keydown.escape.prevent="cancelEdit"
                @click.stop />
            </template>

            <!-- Field-type cell renderer (registry) -->
            <template v-else>
              <a
                v-if="rowHref(row)"
                :href="rowHref(row)!"
                class="block"
                :class="{ 'font-semibold text-primary hover:underline': ci === 0 && !['Image', 'Attach', 'Check'].includes(getFieldType(col.key)) }"
                @click.stop="onRowAnchorClick($event, row)"
              >
                <component :is="getListCell(getFieldType(col.key)) ?? DefaultListCell" :value="row[col.key]" :row="row"
                  :field="fieldMap[col.key] ?? { fieldname: col.key, fieldtype: 'Data', label: col.label }"
                  :status-config="statusConfig" />
              </a>
              <div
                v-else
                :class="{ 'font-semibold text-primary hover:underline': ci === 0 && !['Image', 'Attach', 'Check'].includes(getFieldType(col.key)) }"
              >
                <component :is="getListCell(getFieldType(col.key)) ?? DefaultListCell" :value="row[col.key]" :row="row"
                  :field="fieldMap[col.key] ?? { fieldname: col.key, fieldtype: 'Data', label: col.label }"
                  :status-config="statusConfig" />
              </div>
            </template>
          </div>
        </TableCell>
      </TableRow>
    </TableBody>
  </Table>
</template>
