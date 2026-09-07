<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { VueDraggable } from 'vue-draggable-plus'
import type { DocField, DocType } from '@/types'
import { metaApi, docsApi } from '@/core/api'
import { Plus, Trash2, Copy, ChevronDown, TriangleAlert, X, ArrowUp, ArrowDown, ClipboardCopy, PencilLine } from '@lucide/vue'
import FieldRenderer from '@/core/renderer/FieldRenderer.vue'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import { getLayoutTypeSet } from '@/core/fieldRegistry'
import { toast } from '@/core/composables/useToast'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import TableEditRow from './TableEditRow.vue'
import { INLINE_TYPES } from './constants'
import { useTableCell, isSubtotalRow } from './useTableCell'
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
const rootRef = ref<HTMLElement | null>(null)
const childDocType = ref<DocType | null>(null)
const rows = ref<Record<string, unknown>[]>([])
const loading = ref(false)

const editIdx = ref<number | null>(null)
const editDraft = ref<Record<string, unknown>>({})
const selectedRows = ref<Set<string>>(new Set())
const selectedTableRows = ref<Array<Record<string, unknown>>>([])

// ── Constants ─────────────────────────────────────────────────────────────────

const LAYOUT_TYPES = getLayoutTypeSet()

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

// Client-only stable identity for each row — survives reorder / add / delete so
// selection, focus and :key stay put. Harmless in the payload: the backend
// regenerates child-row `name`/`idx` and ignores unknown keys.
function genUid(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function adoptRows(incoming: unknown) {
  const arr = Array.isArray(incoming) ? (incoming as Record<string, unknown>[]) : []
  const prev = rows.value
  // Our own echo (same object refs) — nothing to reconcile.
  if (arr.length === prev.length && arr.every((r, i) => r === prev[i])) return

  const byName = new Map<string, Record<string, unknown>>()
  prev.forEach((r) => {
    const key = r.name ?? r.id
    if (key != null) byName.set(String(key), r)
  })

  rows.value = arr.map((r, i) => {
    if (r && typeof r === 'object' && '__uid' in r) return r
    const carrier = (r?.name != null && byName.get(String(r.name))) || prev[i]
    return { ...r, __uid: (carrier?.__uid as string) ?? genUid() }
  })
}

watch(() => props.modelValue, adoptRows, { immediate: true })

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

// User-hidden columns — toggled via the "Columns" dropdown, persisted per
// (child DocType + field) so the choice survives tab switches / reloads.
const colStorageKey = `grunt.tbl.hiddenCols.${props.field.options ?? ''}.${props.field.fieldname}`
const hiddenColumns = ref<Set<string>>(new Set())
try {
  const saved = localStorage.getItem(colStorageKey)
  if (saved) hiddenColumns.value = new Set(JSON.parse(saved) as string[])
} catch { /* private mode / bad JSON — ignore */ }
watch(hiddenColumns, (v) => {
  try { localStorage.setItem(colStorageKey, JSON.stringify([...v])) } catch { /* ignore */ }
})

const displayedColumns = computed(() =>
  tableColumns.value.filter((f) => !hiddenColumns.value.has(f.fieldname)),
)

function toggleColumn(fieldname: string) {
  const next = new Set(hiddenColumns.value)
  if (next.has(fieldname)) {
    next.delete(fieldname)
  } else {
    if (tableColumns.value.length - next.size <= 1) return
    next.add(fieldname)
  }
  hiddenColumns.value = next
}

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

// Grouping / group-ordering is driven solely by the `group_by` field config.
const sortField = computed(() => groupField.value)

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

// ── Quick search (view-only filter over the visible columns) ────────────────

const tableSearch = ref('')

const visibleRows = computed<RowWithMeta[]>(() => {
  const q = tableSearch.value.trim().toLowerCase()
  if (!q) return displayRows.value
  const cols = displayedColumns.value
  return displayRows.value.filter((r) =>
    cols.some((c) => {
      const v = r[`${c.fieldname}__label`] ?? r[c.fieldname]
      return v != null && String(v).toLowerCase().includes(q)
    }),
  )
})

// Reorder is only offered when rows aren't grouped, sorted or filtered.
const canReorder = computed(
  () => !props.disabled && !groupField.value && !sortState.value && !tableSearch.value.trim(),
)

// ── Sort by clicking a column header (commits the new order) ─────────────────

const sortState = ref<{ col: string; dir: 'asc' | 'desc' } | null>(null)

function sortByColumn(f: DocField) {
  if (props.disabled || groupField.value || justResized) return
  const dir: 'asc' | 'desc' =
    sortState.value?.col === f.fieldname && sortState.value.dir === 'asc' ? 'desc' : 'asc'
  const numeric = f.fieldtype === 'Int' || f.fieldtype === 'Float'
  const sorted = [...rows.value].sort((a, b) => {
    const av = a[f.fieldname]
    const bv = b[f.fieldname]
    const aEmpty = av === null || av === undefined || av === ''
    const bEmpty = bv === null || bv === undefined || bv === ''
    if (aEmpty && bEmpty) return 0
    if (aEmpty) return 1 // empties always last
    if (bEmpty) return -1
    const r = numeric
      ? Number(av) - Number(bv)
      : String(av).localeCompare(String(bv), undefined, { numeric: true })
    return dir === 'asc' ? r : -r
  })
  sortState.value = { col: f.fieldname, dir }
  push(sorted)
}

const totalColCount = computed(() =>
  1 /* select */ + 1 /* № */ + displayedColumns.value.length + 1 /* actions */,
)

function isNewGroup(row: Record<string, unknown>, idx: number): boolean {
  if (!groupField.value) return false
  if (idx === 0) return true
  const prev = visibleRows.value[idx - 1] as Record<string, unknown>
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

// ── Column width (drag-to-resize, persisted per child DocType + field) ───────

const COL_MIN_WIDTH: Record<string, string> = {
  Check: '4rem',
  Int: '7rem',
  Float: '7rem',
  Date: '9rem',
  Datetime: '11rem',
  Time: '7rem',
  Select: '9rem',
}

const colWidthKey = `grunt.tbl.colWidths.${props.field.options ?? ''}.${props.field.fieldname}`
const colWidths = ref<Record<string, number>>({})
try {
  const saved = localStorage.getItem(colWidthKey)
  if (saved) colWidths.value = JSON.parse(saved)
} catch { /* ignore */ }
watch(
  colWidths,
  (v) => {
    try { localStorage.setItem(colWidthKey, JSON.stringify(v)) } catch { /* ignore */ }
  },
  { deep: true },
)

function colStyle(f: DocField): string {
  const w = colWidths.value[f.fieldname]
  return w
    ? `width:${w}px;min-width:${w}px;max-width:${w}px`
    : `min-width: ${COL_MIN_WIDTH[f.fieldtype] ?? '8rem'}`
}

let resizeCol: { field: string; startX: number; startW: number } | null = null
let justResized = false

function startColResize(f: DocField, e: MouseEvent) {
  const th = (e.target as HTMLElement).closest('th') as HTMLElement | null
  if (!th) return
  e.preventDefault()
  e.stopPropagation()
  resizeCol = { field: f.fieldname, startX: e.clientX, startW: th.offsetWidth }
  window.addEventListener('mousemove', onColResizeMove)
  window.addEventListener('mouseup', onColResizeEnd, { once: true })
}
function onColResizeMove(e: MouseEvent) {
  if (!resizeCol) return
  const w = Math.max(60, resizeCol.startW + (e.clientX - resizeCol.startX))
  colWidths.value = { ...colWidths.value, [resizeCol.field]: w }
}
function onColResizeEnd() {
  window.removeEventListener('mousemove', onColResizeMove)
  resizeCol = null
  justResized = true
  setTimeout(() => { justResized = false }, 0)
}
onUnmounted(() => window.removeEventListener('mousemove', onColResizeMove))

// ── Row mutations ─────────────────────────────────────────────────────────────

function push(updated: Record<string, unknown>[]) {
  rows.value = updated
  emit('update:modelValue', updated)
}

// drag v-model target: strips DataTable-era meta-fields and reassigns
// idx to match the new visual position so the backend (which sorts child rows
// by idx on load) persists the drag order.
const draggableRows = computed({
  get: () => displayRows.value,
  set: (val: Array<Record<string, unknown>>) => {
    sortState.value = null // manual drag order supersedes any header sort
    const reordered = val.map((row, i) => {
      const { __row_key: _k, __row_index: _i, __display_index: _d, __group_sort_order: _g, ...raw } = row
      raw['idx'] = i
      return raw
    })
    push(reordered)
  },
})

function blankRow(): Record<string, unknown> {
  const r: Record<string, unknown> = { __uid: genUid() }
  allFields.value.forEach((f) => {
    r[f.fieldname] = f.default ?? (f.fieldtype === 'Check' ? false : null)
  })
  return r
}

function addRow() {
  if (!canAddRow.value) return
  const newRow = blankRow()
  push([...rows.value, newRow])
  // Auto-open dialog if the child has fields the inline grid can't fully edit
  if (hasComplexFields.value) {
    openEditor(newRow)
  }
  return newRow
}

function addRowAndFocus() {
  const r = addRow()
  if (r && !hasComplexFields.value) focusCell(r.__uid, 0)
}

// ── Row-level actions (duplicate / insert / delete + undo) ───────────────────

function rowIndex(row: Record<string, unknown>): number {
  return rows.value.findIndex((r) => r.__uid === row.__uid)
}

let lastDeleted: { rows: Record<string, unknown>[]; at: number } | null = null

function undoDelete() {
  if (!lastDeleted) return
  const next = [...rows.value]
  next.splice(Math.min(lastDeleted.at, next.length), 0, ...lastDeleted.rows)
  lastDeleted = null
  push(next)
}

function removeRow(row: Record<string, unknown>) {
  const idx = rowIndex(row)
  if (idx === -1) return
  selectedRows.value.delete(String(row.__uid ?? ''))
  lastDeleted = { rows: [rows.value[idx]], at: idx }
  push(rows.value.filter((_, i) => i !== idx))
  toast.info(t('Row deleted'), t('Deleted'), {
    action: { label: t('Undo'), onClick: undoDelete },
  })
}

function duplicateRow(row: Record<string, unknown>) {
  const idx = rowIndex(row)
  if (idx === -1) return
  const { name: _n, id: _i, __uid: _u, ...rest } = rows.value[idx]
  const next = [...rows.value]
  next.splice(idx + 1, 0, { ...rest, __uid: genUid() })
  push(next)
}

function insertRow(row: Record<string, unknown>, where: 'above' | 'below') {
  const idx = rowIndex(row)
  if (idx === -1) return
  const next = [...rows.value]
  next.splice(where === 'above' ? idx : idx + 1, 0, blankRow())
  push(next)
}

function setCell(row: Record<string, unknown>, fieldname: string, val: unknown) {
  const uid = row.__uid
  push(rows.value.map((r) => (r.__uid === uid ? { ...r, [fieldname]: val } : r)))
}

function numOrNull(v: unknown): number | null {
  if (v === '' || v === null || v === undefined) return null
  const n = Number(v)
  return Number.isNaN(n) ? null : n
}

// ── Paste from spreadsheet (TSV) ─────────────────────────────────────────────

function coercePasted(raw: string, f: DocField): unknown {
  const s = raw.trim()
  if (s === '') return f.fieldtype === 'Check' ? false : null
  switch (f.fieldtype) {
    case 'Int':
    case 'Float':
      return numOrNull(s)
    case 'Check':
      return /^(1|true|yes|y|так|✓|x|on)$/i.test(s)
    case 'Select': {
      const hit = selectOptions(f).find((o) => o.toLowerCase() === s.toLowerCase())
      return hit ?? s
    }
    default:
      return s
  }
}

/** Paste a tab/newline block starting at the focused cell — new rows are
 *  appended as needed. A plain single value falls through to the native paste. */
function onPaste(e: ClipboardEvent) {
  if (props.disabled) return
  const text = e.clipboardData?.getData('text/plain') ?? ''
  if (!text || (!text.includes('\t') && !text.includes('\n'))) return

  const cellEl = (e.target as HTMLElement)?.closest?.('[data-cell]') as HTMLElement | null
  const [anchorUid, anchorColStr] = (cellEl?.dataset.cell ?? '').split(':')
  const anchorCol = Number(anchorColStr)
  if (!anchorUid || Number.isNaN(anchorCol)) return
  e.preventDefault()

  const grid = text
    .replace(/\r\n?/g, '\n')
    .replace(/\n$/, '')
    .split('\n')
    .map((line) => line.split('\t'))

  const cols = displayedColumns.value
  const list = [...rows.value]
  let startIdx = list.findIndex((r) => String(r.__uid) === anchorUid)
  if (startIdx === -1) startIdx = list.length

  grid.forEach((cells, ri) => {
    const rowIdx = startIdx + ri
    if (rowIdx >= list.length) list.push(blankRow())
    const row = { ...list[rowIdx] }
    cells.forEach((raw, ci) => {
      const col = cols[anchorCol + ci]
      if (!col || col.read_only || !INLINE_TYPES.has(col.fieldtype)) return
      row[col.fieldname] = coercePasted(raw, col)
    })
    list[rowIdx] = row
  })
  push(list)
}

// ── Dialog editor ─────────────────────────────────────────────────────────────

function openEditor(row: Record<string, unknown>) {
  const i = rows.value.findIndex((r) => r.__uid === row.__uid)
  if (i === -1) return
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

// ── Cell helpers (shared with TableEditRow) ───────────────────────────────────

const { selectOptions, cellError } = useTableCell(() => displayedColumns.value)

// Move focus to the editable control of another cell (same column, other row).
function focusCell(rowUid: unknown, colIdx: number) {
  nextTick(() => {
    const sel = `[data-cell="${String(rowUid)}:${colIdx}"] input, [data-cell="${String(rowUid)}:${colIdx}"] select, [data-cell="${String(rowUid)}:${colIdx}"] [tabindex]`
    rootRef.value?.querySelector<HTMLElement>(sel)?.focus()
  })
}

// Enter = commit + jump to the same column of the next row (creating one at the
// end). Arrow ↑/↓ navigate rows too — but not inside <select> or number inputs,
// where the arrows have their own native meaning.
function onCellKeydown(e: KeyboardEvent, row: Record<string, unknown>, colIdx: number) {
  const list = rows.value
  const i = list.findIndex((r) => r.__uid === row.__uid)
  if (i === -1) return

  if (e.key === 'Enter') {
    e.preventDefault()
    if (i < list.length - 1) {
      focusCell(list[i + 1].__uid, colIdx)
    } else if (canAddRow.value) {
      addRow()
      focusCell(rows.value[rows.value.length - 1]?.__uid, colIdx)
    }
    return
  }

  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    const el = e.target as HTMLElement
    const nativeArrows = el.tagName === 'SELECT' || (el as HTMLInputElement).type === 'number'
    if (nativeArrows) return
    const target = e.key === 'ArrowDown' ? i + 1 : i - 1
    if (target >= 0 && target < list.length) {
      e.preventDefault()
      focusCell(list[target].__uid, colIdx)
    }
  }
}

// ── Autofill (drag the cell corner to copy a value down/up) ──────────────────

const activeCell = ref<{ uid: string; colIdx: number } | null>(null)
const fillAnchor = ref<{ field: string; value: unknown; anchorIdx: number } | null>(null)
const fillPreviewUids = ref<Set<string>>(new Set())

function startFill(uid: string, colIdx: number) {
  const col = displayedColumns.value[colIdx]
  const anchorIdx = rows.value.findIndex((r) => String(r.__uid) === uid)
  if (!col || anchorIdx === -1) return
  fillAnchor.value = { field: col.fieldname, value: rows.value[anchorIdx][col.fieldname], anchorIdx }
  fillPreviewUids.value = new Set([uid])
  window.addEventListener('mousemove', onFillMove)
  window.addEventListener('mouseup', onFillEnd, { once: true })
}

function onFillMove(e: MouseEvent) {
  if (!fillAnchor.value) return
  const cellEl = (document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null)?.closest(
    '[data-cell]',
  ) as HTMLElement | null
  const uid = (cellEl?.dataset.cell ?? '').split(':')[0]
  if (!uid) return
  const targetIdx = rows.value.findIndex((r) => String(r.__uid) === uid)
  if (targetIdx === -1) return
  const lo = Math.min(fillAnchor.value.anchorIdx, targetIdx)
  const hi = Math.max(fillAnchor.value.anchorIdx, targetIdx)
  fillPreviewUids.value = new Set(rows.value.slice(lo, hi + 1).map((r) => String(r.__uid)))
}

function onFillEnd() {
  window.removeEventListener('mousemove', onFillMove)
  const a = fillAnchor.value
  const uids = fillPreviewUids.value
  if (a && uids.size > 1) {
    push(rows.value.map((r) => (uids.has(String(r.__uid)) ? { ...r, [a.field]: a.value } : r)))
  }
  fillAnchor.value = null
  fillPreviewUids.value = new Set()
}

onUnmounted(() => window.removeEventListener('mousemove', onFillMove))

function rowName(row: Record<string, unknown>, index: number): string {
  const key = row.__uid ?? row.name ?? row.id ?? row.__name ?? row._name
  return key ? String(key) : `idx:${index}`
}

function syncSelectedTableRows() {
  const keys = selectedRows.value
  selectedTableRows.value = rowsWithMeta.value.filter((row) => keys.has(String(row.__row_key)))
}

function emitSelection() {
  emit('selection-change', Array.from(selectedRows.value))
}


function rowSelected(row: RowWithMeta): boolean {
  return !isSubtotalRow(row) && selectedRows.value.has(String(row.__row_key))
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

// ── Select-all (header checkbox) ────────────────────────────────────────────

const selectableKeys = computed(() =>
  rowsWithMeta.value.filter((r) => !isSubtotalRow(r)).map((r) => String(r.__row_key)),
)
const allSelected = computed(
  () => selectableKeys.value.length > 0 && selectableKeys.value.every((k) => selectedRows.value.has(k)),
)
const someSelected = computed(() => selectableKeys.value.some((k) => selectedRows.value.has(k)))
const headerCheckState = computed<boolean | 'indeterminate'>(() =>
  allSelected.value ? true : someSelected.value ? 'indeterminate' : false,
)

function toggleSelectAll() {
  selectedRows.value = allSelected.value ? new Set() : new Set(selectableKeys.value)
  syncSelectedTableRows()
  emitSelection()
}

// ── Quick Entry for Link fields in row dialog ─────────────────────────────────

const quickEntryDt = ref<DocType | null>(null)
const quickEntryPreset = ref<Record<string, unknown>>({})
const quickEntryLinkFieldname = ref<string | null>(null)

// Set when "+ Create" is used from an inline Link cell (vs. the row dialog),
// so the newly-created doc name is written straight back to that row (by uid,
// stable across reorder/delete while the QuickEntry dialog is open).
const quickEntryRowUid = ref<string | null>(null)

async function handleCreateNew(linkedDoctype: string, preset: string, linkFieldname: string) {
  const dt = await metaApi.get(linkedDoctype)
  if (!dt) return
  quickEntryDt.value = dt
  quickEntryPreset.value = preset ? { name: preset } : {}
  quickEntryLinkFieldname.value = linkFieldname
  quickEntryRowUid.value = null
}

function handleInlineCreateNew(rowUid: string, linkedDoctype: string, preset: string, linkFieldname: string) {
  void handleCreateNew(linkedDoctype, preset, linkFieldname)
  quickEntryRowUid.value = rowUid
}

function onQuickEntrySaved(docname: string) {
  const fieldname = quickEntryLinkFieldname.value
  if (quickEntryRowUid.value && fieldname) {
    const uid = quickEntryRowUid.value
    push(rows.value.map((r) => (r.__uid === uid ? { ...r, [fieldname]: docname } : r)))
  } else if (fieldname) {
    updateDraft(fieldname, docname)
  }
  quickEntryDt.value = null
  quickEntryRowUid.value = null
}

// ── Bulk selection actions ────────────────────────────────────────────────────

const selectionCount = computed(() => selectedRows.value.size)

function deleteSelected() {
  const keys = selectedRows.value
  if (!keys.size) return
  const removed = rows.value.filter((row, i) => keys.has(rowName(row, i)))
  const firstIdx = rows.value.findIndex((row, i) => keys.has(rowName(row, i)))
  const remaining = rows.value.filter((row, i) => !keys.has(rowName(row, i)))
  selectedRows.value = new Set()
  selectedTableRows.value = []
  lastDeleted = { rows: removed, at: firstIdx === -1 ? remaining.length : firstIdx }
  push(remaining)
  toast.info(
    `${removed.length} ${removed.length === 1 ? t('row deleted') : t('rows deleted')}`,
    t('Deleted'),
    { action: { label: t('Undo'), onClick: undoDelete } },
  )
}

// Copy the selected rows to the clipboard as TSV (round-trips with paste).
function copySelectedTsv() {
  const keys = selectedRows.value
  const picked = displayRows.value.filter((r) => keys.has(String(r.__row_key)))
  if (!picked.length || !navigator.clipboard) return
  const cols = displayedColumns.value
  const tsv = picked
    .map((r) => cols.map((c) => (r[c.fieldname] == null ? '' : String(r[c.fieldname]))).join('\t'))
    .join('\n')
  navigator.clipboard.writeText(tsv).then(
    () => toast.success(`${picked.length} ${picked.length === 1 ? t('row copied') : t('rows copied')}`),
    () => toast.error(t('Copy failed')),
  )
}

// Keyboard: Delete removes the selection; Ctrl/Cmd+C copies it (both only when
// focus isn't inside a text field, so normal editing is untouched).
function onRootKeydown(e: KeyboardEvent) {
  if (props.disabled || !selectedRows.value.size) return
  const el = e.target as HTMLElement | null
  const inField = !!el && ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)
  if (e.key === 'Delete' && !inField) {
    e.preventDefault()
    deleteSelected()
  } else if ((e.key === 'c' || e.key === 'C') && (e.ctrlKey || e.metaKey) && !inField) {
    e.preventDefault()
    copySelectedTsv()
  }
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
      const { name: _n, id: _i, __uid: _u, ...rest } = row as Record<string, unknown>
      return { ...rest, __uid: genUid() }
    })
  push([...rows.value, ...copies])
  clearSelection()
}

// ── Bulk-edit one column across the selected rows ────────────────────────────

const bulkEditOpen = ref(false)
const bulkCol = ref('')
const bulkVal = ref('')

const bulkEditableColumns = computed(() =>
  displayedColumns.value.filter((f) => !f.read_only && INLINE_TYPES.has(f.fieldtype)),
)

function applyBulkEdit() {
  const col = bulkEditableColumns.value.find((f) => f.fieldname === bulkCol.value)
  if (!col) return
  const keys = selectedRows.value
  const value = coercePasted(bulkVal.value, col)
  push(rows.value.map((r, i) => (keys.has(rowName(r, i)) ? { ...r, [col.fieldname]: value } : r)))
  bulkEditOpen.value = false
  bulkVal.value = ''
}

// ── Inline validation (uses cellError from useTableCell) ─────────────────────

// "Loud" errors only — a bad value, not merely an unfilled required cell.
function rowHasError(row: Record<string, unknown>): boolean {
  return allFields.value.some((f) => cellError(row, f, { includeRequired: false }) !== null)
}

const invalidRowCount = computed(
  () => rows.value.filter((r) => !isSubtotalRow(r) && rowHasError(r)).length,
)

// Block "Add row" while the row you'd be leaving behind is still incomplete —
// stops half-filled rows from piling up (the classic silent-save-error source).
const canAddRow = computed(() => {
  const last = rows.value[rows.value.length - 1]
  return !last || !rowHasError(last)
})
</script>

<template>
  <div ref="rootRef" @paste="onPaste" @keydown="onRootKeydown">
  <div class="flex flex-col gap-2">
    <div
      v-if="field.label || tableColumns.length > 1 || rows.length > 8"
      class="flex items-center gap-2 flex-wrap"
    >
      <span
        v-if="field.label"
        class="flex items-center gap-1 font-medium text-foreground/90 mr-1"
      >
        {{ field.label }}
        <span v-if="field.required" class="text-destructive font-semibold" aria-hidden="true">*</span>
      </span>
      <Input
        v-if="rows.length > 8"
        v-model="tableSearch"
        :placeholder="t('Search rows…')"
        class="h-8 w-52 text-xs"
      />
      <span v-if="tableSearch.trim()" class="text-xs text-muted-foreground whitespace-nowrap">
        {{ visibleRows.length }} / {{ rows.length }}
      </span>
      <DropdownMenu v-if="tableColumns.length > 1">
        <DropdownMenuTrigger as-child>
          <Button variant="outline" size="sm" type="button" class="!text-xs gap-1 shrink-0 ml-auto">
            {{ t('Columns') }}
            <ChevronDown class="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuCheckboxItem
            v-for="f in tableColumns" :key="f.fieldname"
            :model-value="!hiddenColumns.has(f.fieldname)"
            @update:model-value="toggleColumn(f.fieldname)"
            @select.prevent
          >
            {{ f.label }}
          </DropdownMenuCheckboxItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
    <!-- Raw <table> (not shadcn <Table>) so its wrapper doesn't create a second
         scroll container that would break `position: sticky` on the header. -->
    <div class="border border-border rounded-lg overflow-auto max-h-[480px] text-xs">
    <table class="w-full caption-bottom text-sm">
      <TableHeader>
        <TableRow class="hover:bg-transparent [&>th]:sticky [&>th]:top-0 [&>th]:z-20 [&>th]:bg-card [&>th]:border-b [&>th]:border-border">
          <TableHead style="width: 2.5rem" class="text-center py-2.5 !sticky left-0 z-30">
            <Checkbox
              v-if="!disabled && selectableKeys.length"
              :model-value="headerCheckState"
              :aria-label="t('Select all')"
              @update:model-value="toggleSelectAll"
            />
          </TableHead>
          <TableHead style="width: 3rem" class="text-center text-muted-foreground select-none py-2.5 !sticky left-10 z-30 border-r border-border">№</TableHead>
          <TableHead
            v-for="f in displayedColumns" :key="f.fieldname" :style="colStyle(f)"
            class="relative px-3 py-2.5 group/th"
            :class="!disabled && !groupField ? 'cursor-pointer hover:text-foreground select-none' : ''"
            :title="f.description || (!disabled && !groupField ? t('Sort by this column') : undefined)"
            @click="sortByColumn(f)"
          >
            <span class="inline-flex items-center gap-1">
              {{ f.label }}<span v-if="f.required" class="text-destructive">*</span>
              <ArrowUp v-if="sortState?.col === f.fieldname && sortState.dir === 'asc'" class="size-3" />
              <ArrowDown v-else-if="sortState?.col === f.fieldname && sortState.dir === 'desc'" class="size-3" />
            </span>
            <span
              class="absolute -right-1 top-0 h-full w-2 cursor-col-resize opacity-0 group-hover/th:opacity-100 flex items-center justify-center"
              :title="t('Drag to resize')"
              @mousedown="startColResize(f, $event)"
              @click.stop.prevent
            >
              <span class="h-4 w-px bg-border" />
            </span>
          </TableHead>
          <TableHead style="width: 5rem" class="py-2.5" />
        </TableRow>
      </TableHeader>

      <!-- Loading skeleton -->
      <TableBody v-if="loading && !displayRows.length">
        <TableRow v-for="n in 3" :key="`sk-${n}`">
          <TableCell :colspan="totalColCount" class="py-2 px-3">
            <Skeleton class="h-4 w-full" />
          </TableCell>
        </TableRow>
      </TableBody>

      <!-- Empty state -->
      <TableBody v-else-if="!visibleRows.length">
        <TableRow>
          <TableCell :colspan="totalColCount" class="text-center text-muted-foreground text-xs py-8">
            {{ tableSearch.trim() ? t('No matching rows') : t('No rows') }}
          </TableCell>
        </TableRow>
      </TableBody>

      <!-- Reorderable path — never grouped, so exactly one <TableRow> per row -->
      <VueDraggable
        v-else-if="canReorder"
        v-model="draggableRows"
        tag="tbody"
        handle=".row-drag-handle"
        ghost-class="tbl-drag-ghost"
        class="[&_tr:last-child]:border-0"
      >
        <TableEditRow
          v-for="(row, idx) in draggableRows"
          :key="String(row.__row_key)"
          :row="row"
          :columns="displayedColumns"
          :display-index="idx + 1"
          :disabled="disabled"
          :can-reorder="canReorder"
          :selected="rowSelected(row)"
          :has-error="rowHasError(row)"
          :show-editor-button="!!allFields.length"
          @set-cell="(fn: string, v: unknown) => setCell(row, fn, v)"
          @create-new="(dt: string, preset: string, fn: string) => handleInlineCreateNew(String(row.__uid), dt, preset, fn)"
          @edit="openEditor(row)"
          @remove="removeRow(row)"
          @toggle-select="toggleRowSelection(row)"
          @duplicate="duplicateRow(row)"
          @insert-above="insertRow(row, 'above')"
          @insert-below="insertRow(row, 'below')"
          @cell-keydown="(ev: KeyboardEvent, colIdx: number) => onCellKeydown(ev, row, colIdx)"
          @cell-focus="(colIdx: number) => (activeCell = { uid: String(row.__uid), colIdx })"
          @fill-start="(colIdx: number) => startFill(String(row.__uid), colIdx)"
          :fill-handle-col="!disabled && activeCell && activeCell.uid === String(row.__uid) ? activeCell.colIdx : null"
          :fill-preview="fillPreviewUids.has(String(row.__uid))"
        />
      </VueDraggable>

      <!-- Grouped / read-only path — group sub-headers interleave with rows -->
      <TableBody v-else>
        <template v-for="(row, idx) in visibleRows" :key="row.__row_key">
          <TableRow v-if="isNewGroup(row, idx)" class="bg-muted/40 hover:bg-muted/40">
            <TableCell
              :colspan="totalColCount"
              :class="groupHeaderLabel(row) ? 'font-semibold text-xs py-1.5 px-3' : 'hidden-group-header'"
            >{{ groupHeaderLabel(row) }}</TableCell>
          </TableRow>

          <TableEditRow
            :row="row"
            :columns="displayedColumns"
            :display-index="idx + 1"
            :disabled="disabled"
            :can-reorder="canReorder"
            :selected="rowSelected(row)"
            :has-error="rowHasError(row)"
            :show-editor-button="!!allFields.length"
            @set-cell="(fn: string, v: unknown) => setCell(row, fn, v)"
            @create-new="(dt: string, preset: string, fn: string) => handleInlineCreateNew(String(row.__uid), dt, preset, fn)"
            @edit="openEditor(row)"
            @remove="removeRow(row)"
            @toggle-select="toggleRowSelection(row)"
            @duplicate="duplicateRow(row)"
            @insert-above="insertRow(row, 'above')"
            @insert-below="insertRow(row, 'below')"
            @cell-keydown="(ev: KeyboardEvent, colIdx: number) => onCellKeydown(ev, row, colIdx)"
            @cell-focus="(colIdx: number) => (activeCell = { uid: String(row.__uid), colIdx })"
            @fill-start="(colIdx: number) => startFill(String(row.__uid), colIdx)"
            :fill-handle-col="!disabled && activeCell && activeCell.uid === String(row.__uid) ? activeCell.colIdx : null"
            :fill-preview="fillPreviewUids.has(String(row.__uid))"
          />
        </template>
      </TableBody>
    </table>
    </div>

    <!-- Bottom action bar: Add row + bulk selection actions -->
    <div class="flex items-center gap-2 flex-wrap min-h-[2rem]">
      <Button
        variant="ghost" v-if="!disabled" type="button" size="sm" class="text-primary"
        :disabled="!canAddRow"
        :title="canAddRow ? undefined : t('Fill in the current row first')"
        @click="addRowAndFocus"
      >
        <Plus class="size-4 mr-1" />
        {{ t('Add row') }}
      </Button>

      <span v-if="invalidRowCount > 0" class="text-xs text-destructive inline-flex items-center gap-1">
        <TriangleAlert class="size-3.5" />
        {{ invalidRowCount }} {{ invalidRowCount === 1 ? t('row needs attention') : t('rows need attention') }}
      </span>

      <template v-if="!disabled && selectionCount > 0">
        <div class="h-4 w-px bg-border" />
        <span class="text-xs text-muted-foreground">
          {{ t('Selected:') }} <span class="font-semibold text-foreground tabular-nums ml-0.5">{{ selectionCount }}</span>
        </span>
        <Button variant="ghost" size="sm" class="!text-xs gap-1" @click="duplicateSelected">
          <Copy class="size-3.5" />
          {{ t('Duplicate') }}
        </Button>
        <Button variant="ghost" size="sm" class="!text-xs gap-1" @click="copySelectedTsv">
          <ClipboardCopy class="size-3.5" />
          {{ t('Copy') }}
        </Button>

        <Popover v-if="bulkEditableColumns.length" v-model:open="bulkEditOpen">
          <PopoverTrigger as-child>
            <Button variant="ghost" size="sm" class="!text-xs gap-1">
              <PencilLine class="size-3.5" />
              {{ t('Set value') }}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" class="w-64 flex flex-col gap-2">
            <select
              v-model="bulkCol"
              class="h-8 w-full rounded-md border border-input bg-transparent px-2 text-xs text-foreground [&>option]:bg-popover"
            >
              <option value="" disabled>{{ t('Column') }}…</option>
              <option v-for="f in bulkEditableColumns" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</option>
            </select>
            <Input v-model="bulkVal" :placeholder="t('New value')" class="h-8 text-xs" />
            <Button size="sm" class="!text-xs" :disabled="!bulkCol" @click="applyBulkEdit">
              {{ t('Apply to') }} {{ selectionCount }}
            </Button>
          </PopoverContent>
        </Popover>

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

/* Drag ghost — a faint outline of where the row will land */
:deep(.tbl-drag-ghost) {
  opacity: 0.4;
  background: hsl(var(--primary) / 0.06);
  outline: 1px dashed hsl(var(--primary) / 0.4);
  outline-offset: -1px;
}
</style>
