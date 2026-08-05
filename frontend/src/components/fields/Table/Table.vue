<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'
import type { DocField, DocType } from '@/types'
import { metaApi, docsApi } from '@/core/api'
import { Plus, X, Pencil, Trash2, Copy, GripVertical } from '@lucide/vue'
import { Table as ShadcnTable } from '@/components/ui/table'
import FieldRenderer from '@/core/renderer/FieldRenderer.vue'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import { getLayoutTypeSet } from '@/core/fieldRegistry'

interface RowWithMeta extends Record<string, unknown> {
  __row_key: string
  __row_index: number
  __display_index?: number
  __group_sort_order?: number
}

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  'create-new': [doctype: string, preset: string, fieldname: string]
  'selection-change': [rowNames: string[]]
}>()

// ── State ─────────────────────────────────────────────────────────────────────

const { t } = useI18n()
const childDocType = ref<DocType | null>(null)
const rows = ref<Record<string, unknown>[]>([])
const loading = ref(false)

const editIdx = ref<number | null>(null)
const editDraft = ref<Record<string, unknown>>({})
const selectedRows = ref<Set<string>>(new Set())
const selectedTableRows = ref<Array<Record<string, unknown>>>([])

// ── Constants ─────────────────────────────────────────────────────────────────

const LAYOUT_TYPES = getLayoutTypeSet()
const INLINE_TYPES = new Set(['Text', 'Int', 'Float', 'Check', 'Select', 'Date', 'Datetime', 'Time'])

// ── Watchers ──────────────────────────────────────────────────────────────────

watch(
  () => props.field.options,
  async (doctype) => {
    if (!doctype) return
    loading.value = true
    try { childDocType.value = await metaApi.get(doctype) } catch {}
    loading.value = false
  },
  { immediate: true },
)

watch(
  () => props.modelValue,
  (val) => {
    rows.value = Array.isArray(val) ? [...(val as Record<string, unknown>[])] : []
  },
  { immediate: true },
)

watch(
  rows,
  () => {
    const current = new Set(rows.value.map((row, i) => rowName(row, i)))
    selectedRows.value = new Set(Array.from(selectedRows.value).filter((k) => current.has(k)))
    syncSelectedTableRows()
    emitSelection()
  },
  { deep: true },
)

// ── Computed ──────────────────────────────────────────────────────────────────

const allFields = computed(() =>
  (childDocType.value?.fields ?? []).filter((f) => !LAYOUT_TYPES.has(f.fieldtype) && !f.hidden),
)

// A field with dynamic_schema_source (e.g. WebPageBlock.settings) renders a
// different sub-form per row instead of a fixed set of columns — the active
// variant is picked live from `dynamic_schemas` by the sibling field named
// in `dynamic_schema_key` (e.g. block_type), read from the row being edited.
const dynamicSchemaField = computed(() =>
  (childDocType.value?.fields ?? []).find((f) => f.dynamic_schema_source),
)

const activeDynamicFields = computed((): DocField[] => {
  const f = dynamicSchemaField.value
  if (!f || !f.dynamic_schema_key) return []
  const variantKey = editDraft.value[f.dynamic_schema_key] as string | undefined
  if (!variantKey) return []
  return f.dynamic_schemas?.[variantKey] ?? []
})

const tableColumns = computed(() => {
  const listView = allFields.value.filter((f) => {
    if (!f.in_list_view) return false
    if (props.doc) {
      const toggleKey = `show_${f.fieldname}`
      if (toggleKey in props.doc && !props.doc[toggleKey]) return false
    }
    return true
  })
  if (listView.length) return listView
  return allFields.value.filter((f) => INLINE_TYPES.has(f.fieldtype))
})

const hasComplexFields = computed(() =>
  allFields.value.some((f) => !INLINE_TYPES.has(f.fieldtype)),
)

const rowsWithMeta = computed<RowWithMeta[]>(() =>
  rows.value.map((row, i) => ({
    ...row,
    __row_key: rowName(row, i),
    __row_index: i,
  })),
)

const groupField = computed(() => props.field.group_by ?? null)

// Use group_by for sorting when enabled, otherwise fall back to Department link field.
const sortField = computed(() => {
  if (groupField.value) return groupField.value
  const departmentField = allFields.value.find((f) => f.fieldname === 'department' && f.fieldtype === 'Link')
  return departmentField?.fieldname ?? null
})

// sort_order map: link field value → sort_order number (from linked DocType)
const groupSortMap = ref<Map<string, number>>(new Map())

// Fetch sort_order values for the active link sort field
watch(
  [sortField, childDocType, rows],
  async ([sf, cdt]) => {
    if (!sf || !cdt) { groupSortMap.value = new Map(); return }
    const fieldDef = cdt.fields.find((f) => f.fieldname === sf)
    if (fieldDef?.fieldtype !== 'Link' || !fieldDef.options) { groupSortMap.value = new Map(); return }
    try {
      const res = await docsApi.list(fieldDef.options, { fields: 'id,name,sort_order', per_page: 9999 })
      const map = new Map<string, number>()
      res.data.forEach((doc, idx) => {
        const so = doc['sort_order']
        const order = so !== null && so !== undefined ? Number(so) : idx
        if (doc.id !== null && doc.id !== undefined) map.set(String(doc.id), order)
        if (doc.name !== null && doc.name !== undefined) map.set(String(doc.name), order)
      })
      groupSortMap.value = map
    } catch {
      groupSortMap.value = new Map()
    }
  },
  { immediate: true },
)

// Sort rows for display: groups appear in the order of their first row in the input array.
// This preserves backend-controlled order (e.g. DFS hierarchy for staffing table) while
// still grouping related rows together for the subheader rendering below.
const displayRows = computed<RowWithMeta[]>(() => {
  if (!sortField.value) return rowsWithMeta.value
  const sf = sortField.value

  // Assign each group a sort index based on first occurrence in input array
  const groupOrder = new Map<string, number>()
  rowsWithMeta.value.forEach((row) => {
    const key = String((row as Record<string, unknown>)[sf] ?? '')
    if (!groupOrder.has(key)) groupOrder.set(key, groupOrder.size)
  })

  const prepared = rowsWithMeta.value.map((row) => {
    const key = String((row as Record<string, unknown>)[sf] ?? '')
    return {
      ...row,
      __group_sort_order: groupOrder.get(key) ?? Number.MAX_SAFE_INTEGER,
    }
  })
  const sorted = [...prepared].sort((a, b) => {
    const aOrd = Number((a as Record<string, unknown>).__group_sort_order ?? Number.MAX_SAFE_INTEGER)
    const bOrd = Number((b as Record<string, unknown>).__group_sort_order ?? Number.MAX_SAFE_INTEGER)
    if (aOrd !== bOrd) return aOrd - bOrd
    return Number(a.__row_index ?? 0) - Number(b.__row_index ?? 0)
  })
  return sorted.map((row, idx) => ({
    ...row,
    __display_index: idx + 1,
  }))
})

// Reorder is only offered when rows aren't grouped (grouping already fixes row order).
const canReorder = computed(() => !props.disabled && !groupField.value)

const totalColCount = computed(() =>
  (canReorder.value ? 1 : 0) + 1 /* select */ + 1 /* № */ + tableColumns.value.length + 1 /* actions */,
)

function isNewGroup(row: Record<string, unknown>, idx: number): boolean {
  if (!groupField.value) return false
  if (idx === 0) return true
  const prev = displayRows.value[idx - 1] as Record<string, unknown>
  return row[groupField.value] !== prev[groupField.value]
}

function groupHeaderLabel(data: Record<string, unknown>): string {
  const gf = groupField.value
  if (!gf) return ''
  const fieldDef = allFields.value.find((f) => f.fieldname === gf)
  const val = data[gf]
  if (val === null || val === undefined || val === '') return ''
  if (fieldDef?.fieldtype === 'Link') {
    const label = data[`${gf}__label`]
    // Якщо label явно встановлено як '' — це "позавідомча група", заголовок приховуємо
    if (label === '') return ''
    return String(label ?? val)
  }
  if (fieldDef?.fieldtype === 'Check') return val ? t('Yes') : t('No')
  return String(val)
}

// ── Column width ──────────────────────────────────────────────────────────────

const COL_MIN_WIDTH: Record<string, string> = {
  Check: '4rem',
  Int: '7rem',
  Float: '7rem',
  Date: '9rem',
  Datetime: '11rem',
  Time: '7rem',
  Select: '9rem',
}

function colStyle(f: DocField): string {
  return `min-width: ${COL_MIN_WIDTH[f.fieldtype] ?? '8rem'}`
}

// ── Row mutations ─────────────────────────────────────────────────────────────

function push(updated: Record<string, unknown>[]) {
  rows.value = updated
  emit('update:modelValue', updated)
}

// vuedraggable v-model target: strips DataTable-era meta-fields and reassigns
// idx to match the new visual position so the backend (which sorts child rows
// by idx on load) persists the drag order.
const draggableRows = computed({
  get: () => displayRows.value,
  set: (val: Array<Record<string, unknown>>) => {
    const reordered = val.map((row, i) => {
      const { __row_key: _k, __row_index: _i, __display_index: _d, __group_sort_order: _g, ...raw } = row
      raw['idx'] = i
      return raw
    })
    push(reordered)
  },
})

function addRow() {
  const newRow: Record<string, unknown> = {}
  allFields.value.forEach((f) => {
    newRow[f.fieldname] = f.default ?? (f.fieldtype === 'Check' ? false : null)
  })
  const newRows = [...rows.value, newRow]
  push(newRows)
  // Auto-open dialog if child has complex fields
  if (hasComplexFields.value) {
    openEditor(newRows.length - 1)
  }
}

function removeRow(i: number) {
  selectedRows.value.delete(rowName(rows.value[i], i))
  push(rows.value.filter((_, idx) => idx !== i))
}

function updateCell(rowIdx: number, fieldname: string, val: unknown) {
  push(rows.value.map((row, i) => (i === rowIdx ? { ...row, [fieldname]: val } : row)))
}

// ── Dialog editor ─────────────────────────────────────────────────────────────

function openEditor(i: number) {
  editIdx.value = i
  editDraft.value = { ...rows.value[i] }
}

function saveEditor() {
  if (editIdx.value === null) return
  push(rows.value.map((row, i) => (i === editIdx.value ? { ...editDraft.value } : row)))
  editIdx.value = null
}

function updateDraft(fieldname: string, val: unknown) {
  editDraft.value = { ...editDraft.value, [fieldname]: val }
}

function updateSettingsDraft(fieldname: string, val: unknown) {
  const source = dynamicSchemaField.value?.fieldname
  if (!source) return
  const current = (editDraft.value[source] as Record<string, unknown>) ?? {}
  editDraft.value = { ...editDraft.value, [source]: { ...current, [fieldname]: val } }
}

// ── Cell helpers ──────────────────────────────────────────────────────────────

function selectOptions(f: DocField): string[] {
  return (f.options ?? '').split('\n').filter(Boolean)
}

function onCellKeydown(e: KeyboardEvent, rowIdx: number, colIdx: number) {
  if (e.key === 'Enter' && rowIdx === rows.value.length - 1 && colIdx === tableColumns.value.length - 1) {
    e.preventDefault()
    addRow()
  }
}

function rowName(row: Record<string, unknown>, index: number): string {
  const key = row.name ?? row.id ?? row.__name ?? row._name
  return key ? String(key) : `idx:${index}`
}

function syncSelectedTableRows() {
  const keys = selectedRows.value
  selectedTableRows.value = rowsWithMeta.value.filter((row) => keys.has(String(row.__row_key)))
}

function emitSelection() {
  emit('selection-change', Array.from(selectedRows.value))
}

function isSubtotalRow(row: Record<string, unknown>): boolean {
  return !!(row as Record<string, unknown>)['_is_subtotal']
}

function rowClass(data: Record<string, unknown>): string {
  return isSubtotalRow(data)
    ? 'bg-muted/40 border-t border-border font-semibold'
    : ''
}

function toggleRowSelection(row: Record<string, unknown>) {
  const key = String(row.__row_key)
  const next = new Set(selectedRows.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selectedRows.value = next
  syncSelectedTableRows()
  emitSelection()
}

// ── Quick Entry for Link fields in row dialog ─────────────────────────────────

const quickEntryDt = ref<DocType | null>(null)
const quickEntryPreset = ref<Record<string, unknown>>({})
const quickEntryLinkFieldname = ref<string | null>(null)

async function handleCreateNew(linkedDoctype: string, preset: string, linkFieldname: string) {
  const dt = await metaApi.get(linkedDoctype)
  if (!dt) return
  quickEntryDt.value = dt
  quickEntryPreset.value = preset ? { name: preset } : {}
  quickEntryLinkFieldname.value = linkFieldname
}

function onQuickEntrySaved(docname: string) {
  if (quickEntryLinkFieldname.value) {
    updateDraft(quickEntryLinkFieldname.value, docname)
  }
  quickEntryDt.value = null
}

// ── Bulk selection actions ────────────────────────────────────────────────────

const selectionCount = computed(() => selectedRows.value.size)

function deleteSelected() {
  const keys = selectedRows.value
  const remaining = rows.value.filter((row, i) => !keys.has(rowName(row, i)))
  selectedRows.value = new Set()
  selectedTableRows.value = []
  push(remaining)
}

function clearSelection() {
  selectedRows.value = new Set()
  selectedTableRows.value = []
  emitSelection()
}

function duplicateSelected() {
  const keys = selectedRows.value
  const copies = rows.value
    .filter((row, i) => keys.has(rowName(row, i)))
    .map((row) => {
      const { name: _n, id: _i, ...rest } = row as Record<string, unknown>
      return rest
    })
  push([...rows.value, ...copies])
  clearSelection()
}

// Display value for non-editable cells (complex types or disabled mode)
function cellDisplay(row: Record<string, unknown>, f: DocField): string {
  const val = row[f.fieldname]
  if (val === null || val === undefined || val === '') return ''
  if (f.fieldtype === 'Check') return val ? t('Yes') : t('No')
  return f.fieldtype === 'Link'
    ? String(row[`${f.fieldname}__label`] ?? val)
    : String(val)
}

// Display value for a subtotal row cell
function subtotalCellDisplay(row: Record<string, unknown>, f: DocField): string {
  if (f.fieldname === 'position_title') return 'Разом:'
  if (f.fieldtype === 'Float' || f.fieldtype === 'Int') {
    const val = Number(row[f.fieldname] ?? 0)
    return val.toFixed(2)
  }
  return ''
}
</script>

<template>
  <div>
  <div class="flex flex-col gap-2">
    <div class="border border-border rounded-lg overflow-x-auto text-xs">
    <ShadcnTable class="max-h-[480px]">
      <TableHeader>
        <TableRow class="hover:bg-transparent">
          <TableHead v-if="canReorder" style="width: 2rem" />
          <TableHead style="width: 2.5rem" class="text-center" />
          <TableHead style="width: 3rem" class="text-center text-muted-foreground select-none">№</TableHead>
          <TableHead v-for="f in tableColumns" :key="f.fieldname" :style="colStyle(f)">
            {{ f.label }}<span v-if="f.required" class="text-destructive ml-0.5">*</span>
          </TableHead>
          <TableHead style="width: 5rem" />
        </TableRow>
      </TableHeader>

      <!-- Empty state -->
      <TableBody v-if="!displayRows.length">
        <TableRow>
          <TableCell :colspan="totalColCount" class="text-center text-muted-foreground text-xs py-8">
            <span v-if="loading">{{ t('Loading...') }}</span>
            <span v-else>{{ t('No rows') }}</span>
          </TableCell>
        </TableRow>
      </TableBody>

      <!-- Reorderable rows (only when not grouped) -->
      <draggable
        v-else-if="canReorder"
        v-model="draggableRows"
        tag="tbody"
        item-key="__row_key"
        handle=".row-drag-handle"
        ghost-class="opacity-30"
        class="[&_tr:last-child]:border-0"
      >
        <template #item="{ element: row }">
          <TableRow :class="rowClass(row)">
            <TableCell class="text-center">
              <GripVertical class="row-drag-handle size-3.5 cursor-grab text-muted-foreground/50 mx-auto" />
            </TableCell>
            <TableCell class="text-center" @click.stop>
              <Checkbox v-if="!isSubtotalRow(row)" :model-value="selectedRows.has(String(row.__row_key))" @update:model-value="toggleRowSelection(row)" />
            </TableCell>
            <TableCell class="text-center text-xs text-muted-foreground select-none">
              <span v-if="!isSubtotalRow(row)">{{ Number(row.__display_index ?? (Number(row.__row_index) + 1)) }}</span>
            </TableCell>

            <TableCell v-for="(f, colIdx) in tableColumns" :key="f.fieldname">
              <!-- Subtotal row: bold, "Разом:" in title column, sums in numeric columns -->
              <template v-if="isSubtotalRow(row)">
                <span class="block px-2 py-1 text-xs font-semibold text-foreground">
                  {{ subtotalCellDisplay(row, f) }}
                </span>
              </template>

              <template v-else-if="disabled || f.read_only || !INLINE_TYPES.has(f.fieldtype)">
                <span
                  :class="['block px-2 py-1 text-xs break-words whitespace-pre-wrap', !cellDisplay(row, f) && 'text-muted-foreground/40']"
                >
                  {{ cellDisplay(row, f) || '—' }}
                </span>
              </template>

              <template v-else-if="f.fieldtype === 'Check'">
                <div class="flex justify-center">
                  <input
                    type="checkbox"
                    :checked="Boolean(row[f.fieldname])"
                    class="rounded border-border size-4"
                    @change="updateCell(Number(row.__row_index), f.fieldname, ($event.target as HTMLInputElement).checked)"
                  >
                </div>
              </template>

              <template v-else-if="f.fieldtype === 'Select'">
                <select
                  :value="String(row[f.fieldname] ?? '')"
                  class="w-full px-2 py-1 text-xs border border-transparent rounded-md bg-transparent hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                  @change="updateCell(Number(row.__row_index), f.fieldname, ($event.target as HTMLSelectElement).value)"
                  @keydown="onCellKeydown($event, Number(row.__row_index), colIdx)"
                >
                  <option value="">—</option>
                  <option v-for="opt in selectOptions(f)" :key="opt" :value="opt">{{ opt }}</option>
                </select>
              </template>

              <template v-else-if="f.fieldtype === 'Int' || f.fieldtype === 'Float'">
                <input
                  type="number"
                  :value="row[f.fieldname] ?? ''"
                  :step="f.fieldtype === 'Float' ? 'any' : '1'"
                  class="w-full px-2 py-1 text-xs border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                  @input="updateCell(Number(row.__row_index), f.fieldname, Number(($event.target as HTMLInputElement).value))"
                  @keydown="onCellKeydown($event, Number(row.__row_index), colIdx)"
                >
              </template>

              <template v-else-if="['Date', 'Datetime', 'Time'].includes(f.fieldtype)">
                <input
                  :type="f.fieldtype === 'Date' ? 'date' : f.fieldtype === 'Datetime' ? 'datetime-local' : 'time'"
                  :value="String(row[f.fieldname] ?? '')"
                  class="w-full px-2 py-1 text-xs border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                  @input="updateCell(Number(row.__row_index), f.fieldname, ($event.target as HTMLInputElement).value)"
                  @keydown="onCellKeydown($event, Number(row.__row_index), colIdx)"
                >
              </template>

              <template v-else>
                <input
                  type="text"
                  :value="String(row[f.fieldname] ?? '')"
                  class="w-full px-2 py-1 text-xs border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                  @input="updateCell(Number(row.__row_index), f.fieldname, ($event.target as HTMLInputElement).value)"
                  @keydown="onCellKeydown($event, Number(row.__row_index), colIdx)"
                >
              </template>
            </TableCell>

            <TableCell>
              <div class="flex items-center justify-end gap-0.5">
                <button
                  v-if="allFields.length && !isSubtotalRow(row)"
                  type="button"
                  class="p-1 rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                  :title="disabled ? t('View') : t('Edit')"
                  @click="openEditor(Number(row.__row_index))"
                >
                  <Pencil class="size-3.5" />
                </button>
                <button
                  v-if="!disabled && !isSubtotalRow(row)"
                  type="button"
                  class="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                  :title="t('Delete row')"
                  @click="removeRow(Number(row.__row_index))"
                >
                  <X class="size-3.5" />
                </button>
              </div>
            </TableCell>
          </TableRow>
        </template>
      </draggable>

      <!-- Plain (grouped or read-only) rows -->
      <TableBody v-else>
        <template v-for="(row, idx) in displayRows" :key="row.__row_key">
          <TableRow v-if="isNewGroup(row, idx)" class="bg-muted/40">
            <TableCell
              :colspan="totalColCount"
              :class="groupHeaderLabel(row) ? 'font-semibold text-xs py-1.5 px-3' : 'hidden-group-header'"
            >{{ groupHeaderLabel(row) }}</TableCell>
          </TableRow>

          <TableRow :class="rowClass(row)">
            <TableCell class="text-center" @click.stop>
              <Checkbox v-if="!isSubtotalRow(row)" :model-value="selectedRows.has(String(row.__row_key))" @update:model-value="toggleRowSelection(row)" />
            </TableCell>
            <TableCell class="text-center text-xs text-muted-foreground select-none">
              <span v-if="!isSubtotalRow(row)">{{ Number(row.__display_index ?? (Number(row.__row_index) + 1)) }}</span>
            </TableCell>

            <TableCell v-for="(f, colIdx) in tableColumns" :key="f.fieldname">
              <template v-if="isSubtotalRow(row)">
                <span class="block px-2 py-1 text-xs font-semibold text-foreground">
                  {{ subtotalCellDisplay(row, f) }}
                </span>
              </template>

              <template v-else-if="disabled || f.read_only || !INLINE_TYPES.has(f.fieldtype)">
                <span
                  :class="['block px-2 py-1 text-xs break-words whitespace-pre-wrap', !cellDisplay(row, f) && 'text-muted-foreground/40']"
                >
                  {{ cellDisplay(row, f) || '—' }}
                </span>
              </template>

              <template v-else-if="f.fieldtype === 'Check'">
                <div class="flex justify-center">
                  <input
                    type="checkbox"
                    :checked="Boolean(row[f.fieldname])"
                    class="rounded border-border size-4"
                    @change="updateCell(Number(row.__row_index), f.fieldname, ($event.target as HTMLInputElement).checked)"
                  >
                </div>
              </template>

              <template v-else-if="f.fieldtype === 'Select'">
                <select
                  :value="String(row[f.fieldname] ?? '')"
                  class="w-full px-2 py-1 text-xs border border-transparent rounded-md bg-transparent hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                  @change="updateCell(Number(row.__row_index), f.fieldname, ($event.target as HTMLSelectElement).value)"
                  @keydown="onCellKeydown($event, Number(row.__row_index), colIdx)"
                >
                  <option value="">—</option>
                  <option v-for="opt in selectOptions(f)" :key="opt" :value="opt">{{ opt }}</option>
                </select>
              </template>

              <template v-else-if="f.fieldtype === 'Int' || f.fieldtype === 'Float'">
                <input
                  type="number"
                  :value="row[f.fieldname] ?? ''"
                  :step="f.fieldtype === 'Float' ? 'any' : '1'"
                  class="w-full px-2 py-1 text-xs border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                  @input="updateCell(Number(row.__row_index), f.fieldname, Number(($event.target as HTMLInputElement).value))"
                  @keydown="onCellKeydown($event, Number(row.__row_index), colIdx)"
                >
              </template>

              <template v-else-if="['Date', 'Datetime', 'Time'].includes(f.fieldtype)">
                <input
                  :type="f.fieldtype === 'Date' ? 'date' : f.fieldtype === 'Datetime' ? 'datetime-local' : 'time'"
                  :value="String(row[f.fieldname] ?? '')"
                  class="w-full px-2 py-1 text-xs border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                  @input="updateCell(Number(row.__row_index), f.fieldname, ($event.target as HTMLInputElement).value)"
                  @keydown="onCellKeydown($event, Number(row.__row_index), colIdx)"
                >
              </template>

              <template v-else>
                <input
                  type="text"
                  :value="String(row[f.fieldname] ?? '')"
                  class="w-full px-2 py-1 text-xs border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                  @input="updateCell(Number(row.__row_index), f.fieldname, ($event.target as HTMLInputElement).value)"
                  @keydown="onCellKeydown($event, Number(row.__row_index), colIdx)"
                >
              </template>
            </TableCell>

            <TableCell>
              <div class="flex items-center justify-end gap-0.5">
                <button
                  v-if="allFields.length && !isSubtotalRow(row)"
                  type="button"
                  class="p-1 rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                  :title="disabled ? t('View') : t('Edit')"
                  @click="openEditor(Number(row.__row_index))"
                >
                  <Pencil class="size-3.5" />
                </button>
                <button
                  v-if="!disabled && !isSubtotalRow(row)"
                  type="button"
                  class="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                  :title="t('Delete row')"
                  @click="removeRow(Number(row.__row_index))"
                >
                  <X class="size-3.5" />
                </button>
              </div>
            </TableCell>
          </TableRow>
        </template>
      </TableBody>
    </ShadcnTable>
    </div>

    <!-- Bottom action bar: Add row + bulk selection actions -->
    <div class="flex items-center gap-2 flex-wrap min-h-[2rem]">
      <Button variant="ghost" v-if="!disabled" type="button" size="sm" class="text-primary" @click="addRow">
        <Plus class="size-4 mr-1" />
        {{ t('Add row') }}
      </Button>

      <template v-if="!disabled && selectionCount > 0">
        <div class="h-4 w-px bg-border" />
        <span class="text-xs text-muted-foreground">
          {{ t('Selected:') }} <span class="font-semibold text-foreground tabular-nums ml-0.5">{{ selectionCount }}</span>
        </span>
        <Button
          variant="ghost" size="sm"
          class="!text-xs gap-1"
          @click="duplicateSelected"
        >
          <Copy class="size-3.5" />
          {{ t('Duplicate') }}
        </Button>
        <Button
          variant="ghost" size="sm"
          class="!text-xs gap-1 text-destructive hover:text-destructive"
          @click="deleteSelected"
        >
          <Trash2 class="size-3.5" />
          {{ t('Delete') }}
        </Button>
        <button
          type="button"
          class="p-0.5 rounded text-muted-foreground/60 hover:text-foreground hover:bg-muted/30 transition-colors"
          :title="t('Clear selection')"
          @click="clearSelection"
        >
          <X class="size-3.5" />
        </button>
      </template>
    </div>

    <!-- Row edit dialog -->
    <Dialog :open="editIdx !== null" @update:open="(v: boolean) => { if (!v) editIdx = null }">
      <DialogContent class="max-w-xl p-0 px-6 pb-4 pt-2 max-h-[60vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle class="font-semibold">{{ field.label }} — рядок {{ editIdx !== null ? editIdx + 1 : '' }}</DialogTitle>
      </DialogHeader>
      <div class="flex flex-col gap-4 py-2">
        <FieldRenderer
          v-for="f in allFields"
          :key="f.fieldname"
          :field="f"
          :modelValue="editDraft[f.fieldname]"
          :disabled="disabled"
          :docValues="editDraft"
          @update:modelValue="updateDraft(f.fieldname, $event)"
          @create-new="handleCreateNew"
        />
        <FieldRenderer
          v-for="f in activeDynamicFields"
          :key="f.fieldname"
          :field="f"
          :modelValue="(editDraft[dynamicSchemaField!.fieldname] as Record<string, unknown> | undefined)?.[f.fieldname]"
          :disabled="disabled"
          :docValues="editDraft"
          @update:modelValue="updateSettingsDraft(f.fieldname, $event)"
          @create-new="handleCreateNew"
        />
      </div>
      <DialogFooter>
        <Button variant="ghost" type="button" @click="editIdx = null">{{ t('Cancel') }}</Button>
        <Button v-if="!disabled" type="button" @click="saveEditor">{{ t('Save') }}</Button>
      </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>

  <!-- Quick Entry dialog for Link fields inside row editor -->
  <QuickEntryDialog
    v-if="quickEntryDt"
    :dt="quickEntryDt"
    :preset="quickEntryPreset"
    mode="link"
    @saved="onQuickEntrySaved"
    @close="quickEntryDt = null"
  />

  </div>
</template>

<style scoped>
/* Hide the group-header <tr> when its label is empty (e.g. "Позавідомча група") */
:deep(tr:has(.hidden-group-header)) {
  display: none;
}
</style>
