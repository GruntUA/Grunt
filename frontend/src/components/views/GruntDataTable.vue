<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import { ChevronUp, ChevronDown, ArrowUpDown } from '@lucide/vue'
import type { DocField, DocTypeStatusConfig, PaginationMeta } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { getListCell } from '@/core/listCellRegistry'
import { useAuthStore } from '@/stores/auth'
import DefaultListCell from '@/components/fields/Default/ListCell.vue'
import { Checkbox } from '@/components/ui/checkbox'
import { Table, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { TableBody, TableCell } from '@/components/ui/table'
import ListEmptyState from '@/components/views/ListEmptyState.vue'
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
  meta?: Pick<PaginationMeta, 'unavailable' | 'unavailable_message'>
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

// ── Seen / unseen (track_seen) ────────────────────────────────────────────
// `_seen` is only present in the row when the DocType opts into track_seen and
// the list query requested it. Without it every row is "off" — untouched styling.
const auth = useAuthStore()
const currentEmail = computed(() => auth.user?.email ?? '')

function seenState(row: Record<string, unknown>): 'off' | 'seen' | 'unseen' {
  const seen = row._seen
  if (!Array.isArray(seen)) return 'off'
  return seen.includes(currentEmail.value) ? 'seen' : 'unseen'
}

/** First-column (title) class — dim once the current user has opened the row. */
function firstColClass(row: Record<string, unknown>, key: string): string {
  if (['Image', 'Attach', 'Check'].includes(getFieldType(key))) return ''
  switch (seenState(row)) {
    case 'seen':
      return 'font-normal text-muted-foreground hover:underline'
    case 'unseen':
      return 'font-semibold text-foreground hover:underline'
    default:
      return 'font-semibold text-primary hover:underline'
  }
}

// ── Inline editing ────────────────────────────────────────────────────────
interface InlineEdit { rowId: string; field: string; value: string }
const inlineEdit = ref<InlineEdit | null>(null)
// shadcn <Input> renders a bare <input> as its root, so the component
// instance's $el is the DOM node we focus.
const inlineInput = ref<{ $el?: HTMLInputElement } | null>(null)

const INLINE_SKIP = new Set(['Check', 'Select', 'Date', 'Datetime', 'Image', 'Attach', 'RichText', 'JSON', 'Code', 'Signature', 'Link', 'Rating', 'Icon'])

function isEditing(rowId: string, field: string) {
  return inlineEdit.value?.rowId === rowId && inlineEdit.value?.field === field
}

async function startEdit(row: any, field: string, fieldtype: string) {
  if (INLINE_SKIP.has(fieldtype) || props.fields.find(f => f.fieldname === field)?.read_only) return
  inlineEdit.value = { rowId: String(row.id ?? row.name ?? ''), field, value: String(row[field] ?? '') }
  await nextTick()
  inlineInput.value?.$el?.focus()
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

function isRowSelected(row: Record<string, unknown>): boolean {
  return !!props.allSelected || props.selectedIds.includes(getRowDocId(row) ?? '')
}
</script>

<template>
  <Table class="w-full">
    <TableHeader v-if="!hideHeader">
      <TableRow class="hover:bg-transparent border-0">
        <TableHead style="width: 3rem" class="px-3 py-2.5 border-b border-border/40">
          <div class="flex items-center justify-center w-full">
            <Checkbox :model-value="isAllSelected()" @update:model-value="emit('selectAll')" />
          </div>
        </TableHead>
        <TableHead v-for="col in columns" :key="col.key"
          class="px-3 py-2.5 font-semibold border-b border-border/40 text-left transition-colors"
          :class="sortKey === col.key ? 'text-foreground' : 'text-muted-foreground hover:text-foreground/80'"
          :role="col.sortable ? 'button' : undefined" @click="col.sortable && emit('sort', col.key)">
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
        <TableCell :colspan="columns.length + 1" class="border-0 p-0">
          <ListEmptyState class="py-16" :meta="meta" />
        </TableCell>
      </TableRow>

      <!-- Rows -->
      <TableRow v-for="(row, ri) in rows" :key="getRowDocId(row) ?? ri"
        class="cursor-pointer border-b border-border/20 last:border-0 transition-colors hover:bg-primary/5"
        :class="{ 'bg-primary/5 hover:bg-primary/10': isRowSelected(row) }" @click="emit('rowClick', row)">
        <TableCell class="relative px-3 py-2.5 border-b border-border/10">
          <div v-if="isRowSelected(row)"
            class="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-r-full pointer-events-none" />
          <span v-else-if="seenState(row) === 'unseen'"
            class="absolute left-1 top-1/2 -translate-y-1/2 size-1.5 rounded-full bg-primary pointer-events-none"
            title="Не переглянуто" aria-hidden="true" />
          <div class="flex items-center justify-center w-full">
            <Checkbox :model-value="isRowSelected(row)"
              @update:model-value="() => { const docId = getRowDocId(row); if (docId) emit('select', docId) }"
              @click.stop />
          </div>
        </TableCell>

        <TableCell v-for="(col, ci) in columns" :key="col.key"
          class="px-3 py-2.5 border-b border-border/10 max-w-xs whitespace-normal wrap-break-word">
          <div @dblclick.stop="ci > 0 && startEdit(row, col.key, getFieldType(col.key))">
            <!-- Inline edit input -->
            <template v-if="isEditing(getRowDocId(row) ?? '', col.key)">
              <Input ref="inlineInput" v-model="inlineEdit!.value" class="h-8 border-primary" @blur="commitEdit"
                @keydown.enter.prevent="commitEdit" @keydown.escape.prevent="cancelEdit" @click.stop />
            </template>

            <!-- Field-type cell renderer (registry) -->
            <template v-else>
              <a v-if="rowHref(row)" :href="rowHref(row)!" class="block"
                :class="ci === 0 ? firstColClass(row, col.key) : (seenState(row) === 'seen' ? 'text-muted-foreground/70' : '')"
                @click.stop="onRowAnchorClick($event, row)">
                <component :is="getListCell(getFieldType(col.key)) ?? DefaultListCell" :value="row[col.key]" :row="row"
                  :field="fieldMap[col.key] ?? { fieldname: col.key, fieldtype: 'Data', label: col.label }"
                  :status-config="statusConfig" />
              </a>
              <div v-else
                :class="ci === 0 ? firstColClass(row, col.key) : (seenState(row) === 'seen' ? 'text-muted-foreground/70' : '')">
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
