<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField, DocType } from '@/types'
import { metaApi, docsApi } from '@/core/api'
import { Plus, X, Pencil, Trash2, CheckSquare } from '@lucide/vue'
import FieldRenderer from '@/core/renderer/FieldRenderer.vue'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import { getLayoutTypeSet } from '@/core/fieldRegistry'

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

const tableColumns = computed(() => {
  const listView = allFields.value.filter((f) => f.in_list_view)
  if (listView.length) return listView
  return allFields.value.filter((f) => INLINE_TYPES.has(f.fieldtype))
})

const hasComplexFields = computed(() =>
  allFields.value.some((f) => !INLINE_TYPES.has(f.fieldtype)),
)

const rowsWithMeta = computed(() =>
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

// Pre-sort rows by linked DocType sort_order (Department fallback) for stable visual order
const displayRows = computed(() => {
  if (!sortField.value) return rowsWithMeta.value
  const sf = sortField.value
  const sortMap = groupSortMap.value
  const prepared = rowsWithMeta.value.map((row) => {
    const key = String((row as Record<string, unknown>)[sf] ?? '')
    const ord = sortMap.has(key) ? sortMap.get(key)! : Number.MAX_SAFE_INTEGER
    return {
      ...row,
      __group_sort_order: ord,
    }
  })
  const sorted = [...prepared].sort((a, b) => {
    const aKey = String((a as Record<string, unknown>)[sf] ?? '')
    const bKey = String((b as Record<string, unknown>)[sf] ?? '')
    if (sortMap.size > 0) {
      const aOrd = Number((a as Record<string, unknown>).__group_sort_order ?? Number.MAX_SAFE_INTEGER)
      const bOrd = Number((b as Record<string, unknown>).__group_sort_order ?? Number.MAX_SAFE_INTEGER)
      if (aOrd !== bOrd) return aOrd - bOrd
    }
    return aKey.localeCompare(bKey)
  })
  return sorted.map((row, idx) => ({
    ...row,
    __display_index: idx + 1,
  }))
})

const dataTableSortField = computed(() => {
  if (!groupField.value) return undefined
  return groupSortMap.value.size > 0 ? '__group_sort_order' : groupField.value
})

const dataTableSortOrder = computed(() =>
  groupField.value ? 1 : undefined,
)

function groupHeaderLabel(data: Record<string, unknown>): string {
  const gf = groupField.value
  if (!gf) return ''
  const fieldDef = allFields.value.find((f) => f.fieldname === gf)
  const val = data[gf]
  if (val === null || val === undefined || val === '') return t('(not set)')
  if (fieldDef?.fieldtype === 'Link') return String(data[`${gf}__label`] ?? val)
  if (fieldDef?.fieldtype === 'Check') return val ? t('Yes') : t('No')
  return String(val)
}

// ── Column width ──────────────────────────────────────────────────────────────

const COL_WIDTH: Record<string, string> = {
  Check: 'w-16',
  Int: 'w-28',
  Float: 'w-28',
  Date: 'w-36',
  Datetime: 'w-44',
  Time: 'w-28',
  Select: 'w-36',
}

function colClass(f: DocField): string {
  return COL_WIDTH[f.fieldtype] ?? 'min-w-[120px]'
}

// ── Row mutations ─────────────────────────────────────────────────────────────

function push(updated: Record<string, unknown>[]) {
  rows.value = updated
  emit('update:modelValue', updated)
}

function onRowReorder(event: { value?: Array<Record<string, unknown>> }) {
  const reordered = (event.value ?? []).map((row) => {
    const { __row_key: _k, __row_index: _i, __display_index: _d, __group_sort_order: _g, ...raw } = row
    return raw
  })
  push(reordered)
}

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

function onSelectionUpdate(selection: Array<Record<string, unknown>> | null | undefined) {
  const next = new Set<string>()
  for (const row of selection ?? []) {
    const key = row.__row_key
    if (key !== null && key !== undefined) next.add(String(key))
  }
  selectedRows.value = next
  selectedTableRows.value = rowsWithMeta.value.filter((row) => next.has(String(row.__row_key)))
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

// Display value for non-editable cells (complex types or disabled mode)
function cellDisplay(row: Record<string, unknown>, f: DocField): string {
  const val = row[f.fieldname]
  if (val === null || val === undefined || val === '') return ''
  if (f.fieldtype === 'Check') return val ? t('Yes') : t('No')
  return f.fieldtype === 'Link'
    ? String(row[`${f.fieldname}__label`] ?? val)
    : String(val)
}
</script>

<template>
  <div>
  <div class="flex flex-col gap-2">
    <DataTable
      :value="displayRows"
      dataKey="__row_key"
      class="border border-border rounded-lg overflow-hidden"
      size="small"
      rowHover
      :selection="selectedTableRows"
      :rowGroupMode="groupField ? 'subheader' : undefined"
      :groupRowsBy="groupField || undefined"
      :sortField="dataTableSortField"
      :sortOrder="dataTableSortOrder"
      @update:selection="onSelectionUpdate"
      @rowReorder="onRowReorder"
    >
      <Column v-if="!disabled && !groupField" rowReorder headerStyle="width: 2rem" />
      <Column selectionMode="multiple" headerStyle="width: 2.5rem" bodyStyle="text-align: center" />

      <Column header="№" headerStyle="width: 3rem" bodyClass="text-center text-xs text-muted-foreground select-none">
        <template #body="{ data }">
            {{ Number(data.__display_index ?? (Number(data.__row_index) + 1)) }}
        </template>
      </Column>

      <Column
        v-for="(f, colIdx) in tableColumns"
        :key="f.fieldname"
        :field="f.fieldname"
        :class="colClass(f)"
      >
        <template #header>
          {{ f.label }}<span v-if="f.required" class="text-destructive ml-0.5">*</span>
        </template>

        <template #body="{ data }">
          <template v-if="disabled || !INLINE_TYPES.has(f.fieldtype)">
            <span
              :class="['block px-2 py-1 text-sm break-words whitespace-pre-wrap', !cellDisplay(data, f) && 'text-muted-foreground/40']"
            >
              {{ cellDisplay(data, f) || '—' }}
            </span>
          </template>

          <template v-else-if="f.fieldtype === 'Check'">
            <div class="flex justify-center">
              <input
                type="checkbox"
                :checked="Boolean(data[f.fieldname])"
                class="rounded border-border size-4"
                @change="updateCell(Number(data.__row_index), f.fieldname, ($event.target as HTMLInputElement).checked)"
              />
            </div>
          </template>

          <template v-else-if="f.fieldtype === 'Select'">
            <select
              :value="String(data[f.fieldname] ?? '')"
              class="w-full px-2 py-1 text-sm border border-transparent rounded-md bg-transparent hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
              @change="updateCell(Number(data.__row_index), f.fieldname, ($event.target as HTMLSelectElement).value)"
              @keydown="onCellKeydown($event, Number(data.__row_index), colIdx)"
            >
              <option value="">—</option>
              <option v-for="opt in selectOptions(f)" :key="opt" :value="opt">{{ opt }}</option>
            </select>
          </template>

          <template v-else-if="f.fieldtype === 'Int' || f.fieldtype === 'Float'">
            <input
              type="number"
              :value="data[f.fieldname] ?? ''"
              :step="f.fieldtype === 'Float' ? 'any' : '1'"
              class="w-full px-2 py-1 text-sm border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
              @input="updateCell(Number(data.__row_index), f.fieldname, Number(($event.target as HTMLInputElement).value))"
              @keydown="onCellKeydown($event, Number(data.__row_index), colIdx)"
            />
          </template>

          <template v-else-if="['Date', 'Datetime', 'Time'].includes(f.fieldtype)">
            <input
              :type="f.fieldtype === 'Date' ? 'date' : f.fieldtype === 'Datetime' ? 'datetime-local' : 'time'"
              :value="String(data[f.fieldname] ?? '')"
              class="w-full px-2 py-1 text-sm border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
              @input="updateCell(Number(data.__row_index), f.fieldname, ($event.target as HTMLInputElement).value)"
              @keydown="onCellKeydown($event, Number(data.__row_index), colIdx)"
            />
          </template>

          <template v-else>
            <input
              type="text"
              :value="String(data[f.fieldname] ?? '')"
              class="w-full px-2 py-1 text-sm border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
              @input="updateCell(Number(data.__row_index), f.fieldname, ($event.target as HTMLInputElement).value)"
              @keydown="onCellKeydown($event, Number(data.__row_index), colIdx)"
            />
          </template>
        </template>
      </Column>

      <Column headerStyle="width: 5rem" bodyStyle="padding: 0.25rem 0.5rem">
        <template #body="{ data }">
          <div class="flex items-center justify-end gap-0.5">
            <button
              v-if="allFields.length"
              type="button"
              class="p-1 rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
              :title="disabled ? t('View') : t('Edit')"
              @click="openEditor(Number(data.__row_index))"
            >
              <Pencil class="size-3.5" />
            </button>
            <button
              v-if="!disabled"
              type="button"
              class="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
              :title="t('Delete row')"
              @click="removeRow(Number(data.__row_index))"
            >
              <X class="size-3.5" />
            </button>
          </div>
        </template>
      </Column>

      <template v-if="groupField" #groupheader="{ data }">
        <span class="font-semibold text-sm">{{ groupHeaderLabel(data) }}</span>
      </template>

      <template #empty>
        <div class="px-3 py-8 text-center text-muted-foreground text-sm">
          <span v-if="loading">{{ t('Loading...') }}</span>
          <span v-else>{{ t('No rows') }}</span>
        </div>
      </template>
    </DataTable>

    <!-- Add row -->
    <Button
      v-if="!disabled"
      type="button" text size="small"
      class="self-start text-primary"
      @click="addRow"
    >
      <Plus class="size-4 mr-1" />
      {{ t('Add row') }}
    </Button>

    <!-- Row edit dialog -->
    <Dialog :visible="editIdx !== null" modal
      :pt="{ root: { class: 'max-w-xl' }, content: { class: 'p-0 px-6 pb-4 pt-2 max-h-[60vh] overflow-y-auto' } }"
      @update:visible="(v: boolean) => { if (!v) editIdx = null }">
      <template #header>
        <span class="font-semibold">{{ field.label }} — рядок {{ editIdx !== null ? editIdx + 1 : '' }}</span>
      </template>
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
      </div>
      <template #footer>
        <Button text type="button" @click="editIdx = null">{{ t('Cancel') }}</Button>
        <Button v-if="!disabled" type="button" @click="saveEditor">{{ t('Save') }}</Button>
      </template>
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

  <!-- Floating bulk action bar (fixed at bottom of screen) -->
  <Teleport to="body">
    <Transition
      enter-active-class="transition-all duration-200 ease-out"
      enter-from-class="opacity-0 translate-y-4"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition-all duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-4"
    >
      <div
        v-if="!disabled && selectionCount > 0"
        class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-5 py-3 bg-card/80 backdrop-blur-xl rounded-2xl border border-primary/20 shadow-2xl shadow-primary/10 ring-1 ring-primary/20 overflow-hidden min-w-[320px]"
      >
        <div class="absolute -right-8 -top-8 size-28 bg-primary/10 rounded-full blur-3xl pointer-events-none" />
        <div class="absolute -left-8 -bottom-8 size-24 bg-primary/5 rounded-full blur-3xl pointer-events-none" />
        <div class="flex items-center gap-2 shrink-0 relative z-10">
          <CheckSquare class="size-4 text-primary" />
          <span class="text-sm font-bold text-foreground">
            {{ t('Selected:') }} <span class="text-primary tabular-nums ml-1">{{ selectionCount }}</span>
          </span>
        </div>
        <div class="h-5 w-px bg-primary/20 relative z-10" />
        <div class="flex items-center gap-1.5 p-1 bg-background/60 backdrop-blur-sm rounded-xl border border-primary/10 relative z-10">
          <Button
            severity="danger" text size="small"
            class="!px-3 !h-7 !text-xs !font-bold gap-1.5 hover:!bg-destructive/10"
            @click="deleteSelected"
          >
            <Trash2 class="size-3.5" />
            <span>{{ t('Delete') }}</span>
          </Button>
        </div>
        <button
          type="button"
          class="ml-auto p-1 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-muted/20 transition-colors relative z-10"
          :title="t('Clear selection')"
          @click="clearSelection"
        >
          <X class="size-4" />
        </button>
      </div>
    </Transition>
  </Teleport>
  </div>
</template>
