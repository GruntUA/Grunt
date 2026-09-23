<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { VueDraggable } from 'vue-draggable-plus'
import {
  ArrowDown,
  ArrowUp,
  Copy,
  GripVertical,
  MoreHorizontal,
  PanelRightOpen,
  PencilLine,
  Plus,
  Trash2,
  TriangleAlert,
  X,
} from '@lucide/vue'
import type { DocField, DocType } from '@/types'
import { metaApi } from '@/core/api'
import { getAsyncFieldComponent, getLayoutTypeSet } from '@/core/fieldRegistry'
import { toast } from '@/core/composables/useToast'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import SelectListCell from '@/components/fields/Select/ListCell.vue'
import { statusConfigOf } from '@/core/status'
import TableRowSheet from './TableRowSheet.vue'
import { INLINE_TYPES, isLayoutRow, useTableCell } from './useTableCell'
import { useTableRows, type Row } from './useTableRows'

/**
 * Child-table field. Simple columns are edited right in the grid; the full row
 * (every field, including the ones the grid can't show) opens in a side sheet.
 * Rows can be dragged to reorder, selected for bulk actions, and deleted with
 * undo. With `field.group_by` rows are shown under group headings (no reorder).
 */
const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  'selection-change': [rowNames: string[]]
}>()

const { t } = useI18n()
const { cellError, cellDisplay } = useTableCell()
const LAYOUT_TYPES = getLayoutTypeSet()

// ── Child DocType & columns ─────────────────────────────────────────────────
const childDocType = ref<DocType | null>(null)
const loading = ref(false)

watch(
  () => props.field.options,
  async (doctype) => {
    if (!doctype) return
    loading.value = true
    try {
      childDocType.value = await metaApi.get(doctype)
    } catch {
      childDocType.value = null
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

const fields = computed(() =>
  (childDocType.value?.fields ?? []).filter((f) => !LAYOUT_TYPES.has(f.fieldtype) && !f.hidden),
)

/** in_list_view fields (a parent `show_<field>` flag can hide one), else every inline-editable field. */
const columns = computed(() => {
  const visible = (f: DocField) => !props.doc || props.doc[`show_${f.fieldname}`] !== false
  const listed = fields.value.filter((f) => f.in_list_view && visible(f))
  return listed.length ? listed : fields.value.filter((f) => INLINE_TYPES.has(f.fieldtype))
})

/** A (usually hidden) field whose sub-form varies per row — see TableRowSheet. */
const dynamicField = computed(() => childDocType.value?.fields.find((f) => f.dynamic_schema_source))

/** Some fields live only in the row sheet — offer the "open row" action. */
const hasSheetOnlyFields = computed(() =>
  fields.value.some((f) => !columns.value.includes(f) || !INLINE_TYPES.has(f.fieldtype)),
)

function blankRow(): Record<string, unknown> {
  return Object.fromEntries(
    fields.value.map((f) => [f.fieldname, f.default ?? (f.fieldtype === 'Check' ? false : null)]),
  )
}

// ── Rows ────────────────────────────────────────────────────────────────────
const table = useTableRows({
  modelValue: () => props.modelValue,
  onChange: (rows) => emit('update:modelValue', rows),
  blankRow,
})
const { rows, selected, headerCheck } = table

watch(table.selectedNames, (names) => emit('selection-change', names))

function isInline(row: Row, f: DocField): boolean {
  return !props.disabled && !f.read_only && !isLayoutRow(row) && INLINE_TYPES.has(f.fieldtype)
}

/** "Loud" errors only — a wrong value, not a required cell that is still empty. */
function rowHasError(row: Row): boolean {
  return fields.value.some((f) => cellError(row, f, { includeRequired: false }) !== null)
}
const invalidCount = computed(() => rows.value.filter(rowHasError).length)

// Don't pile up half-filled rows: finish (fix) the last one before adding more.
const canAddRow = computed(() => {
  const last = rows.value[rows.value.length - 1]
  return !last || !rowHasError(last)
})

// The child DocType's status field shows as a coloured badge, like in lists.
const statusConfig = computed(() => statusConfigOf(childDocType.value))

// ── Grouping (field.group_by) ───────────────────────────────────────────────
const groupBy = computed(() => props.field.group_by || null)

function groupLabel(row: Row): string {
  const gf = groupBy.value
  const value = gf ? row[gf] : null
  if (!gf || value === null || value === undefined || value === '') return ''
  const def = fields.value.find((f) => f.fieldname === gf)
  if (def?.fieldtype === 'Check') return value ? t('Yes') : t('No')
  const label = row[`${gf}__label`]
  if (label === '') return '' // explicitly unlabelled group — no heading
  return String(label ?? value)
}

type Item =
  | { kind: 'group'; key: string; label: string }
  | { kind: 'row'; key: string; row: Row; position: number }

/** Rows in display order; groups keep the order of their first row. */
const items = computed<Item[]>(() => {
  const gf = groupBy.value
  if (!gf) return rows.value.map((row, i) => ({ kind: 'row', key: row.__uid, row, position: i + 1 }))

  const groups = new Map<string, Row[]>()
  for (const row of rows.value) {
    const key = String(row[gf] ?? '')
    groups.set(key, [...(groups.get(key) ?? []), row])
  }
  const out: Item[] = []
  let position = 0
  for (const [key, list] of groups) {
    const label = groupLabel(list[0])
    if (label) out.push({ kind: 'group', key: `group:${key}`, label })
    for (const row of list) out.push({ kind: 'row', key: row.__uid, row, position: ++position })
  }
  return out
})

const canReorder = computed(() => !props.disabled && !groupBy.value)

const draggableItems = computed({
  get: () => items.value,
  set: (next: Item[]) =>
    table.reorder(next.flatMap((item) => (item.kind === 'row' ? [item.row] : []))),
})

/** Room an inline editor needs to stay usable (the table scrolls sideways). */
const CELL_WIDTH: Record<string, string> = {
  Check: 'w-12',
  Int: 'min-w-24',
  Float: 'min-w-28',
  Time: 'min-w-28',
  Select: 'min-w-36',
  Date: 'min-w-40',
  Datetime: 'min-w-52',
  Link: 'min-w-56',
  Text: 'min-w-64 whitespace-normal',
  LongText: 'min-w-64 whitespace-normal',
}

const colSpan = computed(() => columns.value.length + (props.disabled ? 2 : 3))

// ── Row actions ─────────────────────────────────────────────────────────────
function addRow() {
  if (!canAddRow.value) return
  const row = table.add()
  // A required field the grid can't edit → go straight to the full form.
  if (fields.value.some((f) => f.required && !(columns.value.includes(f) && INLINE_TYPES.has(f.fieldtype)))) {
    openRow(row.__uid)
  }
}

function deleteRows(count: number) {
  if (!count) return
  const message = count === 1 ? t('Row deleted') : `${count} ${t('rows deleted')}`
  toast.info(message, t('Deleted'), { action: { label: t('Undo'), onClick: table.undoRemove } })
}

// ── Row sheet ───────────────────────────────────────────────────────────────
const editingUid = ref<string | null>(null)
const editingRow = computed(() => rows.value.find((r) => r.__uid === editingUid.value) ?? null)

function openRow(uid: string) {
  editingUid.value = uid
}

function saveRow(data: Record<string, unknown>) {
  if (editingUid.value) table.replace(editingUid.value, data)
  editingUid.value = null
}

// ── Quick entry for "+ Create" in Link fields (grid cell or row sheet) ─────────
const quickEntry = ref<{ doctype: DocType; preset: Record<string, unknown>; apply: (name: string) => void } | null>(null)

async function createLinked(doctype: string, preset: string, apply: (name: string) => void) {
  const dt = await metaApi.get(doctype)
  if (dt) quickEntry.value = { doctype: dt, preset: preset ? { name: preset } : {}, apply }
}

function cellListeners(row: Row, f: DocField) {
  const listeners: Record<string, (...args: never[]) => void> = {
    'update:modelValue': (value: unknown) => table.setCell(row.__uid, f.fieldname, value),
  }
  if (f.fieldtype === 'Link') {
    listeners['create-new'] = (doctype: string, preset: string) =>
      createLinked(doctype, preset, (name) => table.setCell(row.__uid, f.fieldname, name))
  }
  return listeners
}

// ── Bulk: set one column on every selected row ──────────────────────────────
const bulkOpen = ref(false)
const bulkFieldname = ref<string>('')
const bulkValue = ref<unknown>(null)
const bulkColumns = computed(() => columns.value.filter((f) => !f.read_only && INLINE_TYPES.has(f.fieldtype)))
const bulkField = computed(() => bulkColumns.value.find((f) => f.fieldname === bulkFieldname.value) ?? null)

watch(bulkFieldname, () => {
  bulkValue.value = bulkField.value?.fieldtype === 'Check' ? false : null
})

function applyBulk() {
  if (!bulkField.value) return
  table.setSelected(bulkField.value.fieldname, bulkValue.value)
  bulkOpen.value = false
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div v-if="field.label" class="flex items-center gap-2">
      <span class="font-medium">
        {{ field.label }}<span v-if="field.required" class="text-destructive"> *</span>
      </span>
      <Badge v-if="rows.length" variant="secondary">{{ rows.length }}</Badge>
    </div>

    <div class="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead v-if="!disabled" class="w-10">
              <Checkbox
                :model-value="headerCheck"
                :disabled="!rows.length"
                :aria-label="t('Select all')"
                @update:model-value="table.toggleAll()"
              />
            </TableHead>
            <TableHead class="w-12">#</TableHead>
            <TableHead v-for="f in columns" :key="f.fieldname" :title="f.description || undefined">
              {{ f.label }}<span v-if="f.required" class="text-destructive"> *</span>
            </TableHead>
            <TableHead class="w-px" />
          </TableRow>
        </TableHeader>

        <TableBody v-if="loading && !childDocType">
          <TableRow v-for="n in 3" :key="n">
            <TableCell :colspan="colSpan"><Skeleton class="h-5 w-full" /></TableCell>
          </TableRow>
        </TableBody>

        <TableBody v-else-if="!rows.length">
          <TableRow>
            <TableCell :colspan="colSpan" class="h-20 text-center text-muted-foreground">
              {{ t('No rows') }}
            </TableCell>
          </TableRow>
        </TableBody>

        <VueDraggable
          v-else
          v-model="draggableItems"
          tag="tbody"
          data-slot="table-body"
          class="[&_tr:last-child]:border-0"
          handle=".row-handle"
          draggable=".row-item"
          ghost-class="opacity-40"
          :disabled="!canReorder"
        >
          <template v-for="item in draggableItems" :key="item.key">
            <TableRow v-if="item.kind === 'group'" class="bg-muted/50 hover:bg-muted/50">
              <TableCell :colspan="colSpan" class="font-medium">{{ item.label }}</TableCell>
            </TableRow>

            <TableRow
              v-else
              class="row-item"
              :class="[isLayoutRow(item.row) && 'text-muted-foreground', rowHasError(item.row) && 'bg-destructive/5']"
              :data-state="selected.has(item.row.__uid) ? 'selected' : undefined"
            >
              <TableCell v-if="!disabled">
                <Checkbox
                  :model-value="selected.has(item.row.__uid)"
                  :aria-label="t('Select row')"
                  @update:model-value="table.toggle(item.row.__uid)"
                />
              </TableCell>

              <TableCell class="text-muted-foreground tabular-nums">
                <span class="inline-flex items-center gap-1">
                  <GripVertical v-if="canReorder" class="row-handle size-4 cursor-grab active:cursor-grabbing" />
                  {{ item.position }}
                </span>
              </TableCell>

              <TableCell
                v-for="f in columns"
                :key="f.fieldname"
                :class="CELL_WIDTH[f.fieldtype] ?? 'min-w-40'"
                :title="cellError(item.row, f) || undefined"
              >
                <Checkbox
                  v-if="f.fieldtype === 'Check'"
                  :model-value="!!item.row[f.fieldname]"
                  :disabled="!isInline(item.row, f)"
                  :aria-label="f.label"
                  @update:model-value="table.setCell(item.row.__uid, f.fieldname, $event === true)"
                />
                <component
                  :is="getAsyncFieldComponent(f.fieldtype)"
                  v-else-if="isInline(item.row, f)"
                  :field="f"
                  :model-value="item.row[f.fieldname] ?? null"
                  :doc="item.row"
                  :error="cellError(item.row, f) || undefined"
                  v-on="cellListeners(item.row, f)"
                />
                <SelectListCell
                  v-else-if="statusConfig?.field === f.fieldname"
                  :value="item.row[f.fieldname]"
                  :row="item.row"
                  :field="f"
                  :status-config="statusConfig"
                />
                <span v-else :class="!cellDisplay(item.row, f) && 'text-muted-foreground'">
                  {{ cellDisplay(item.row, f) || '—' }}
                </span>
              </TableCell>

              <TableCell>
                <div class="flex items-center justify-end">
                  <Button
                    v-if="hasSheetOnlyFields || disabled"
                    variant="ghost"
                    size="icon"
                    :title="disabled ? t('View') : t('Edit')"
                    :aria-label="disabled ? t('View') : t('Edit')"
                    @click="openRow(item.row.__uid)"
                  >
                    <PanelRightOpen />
                  </Button>
                  <DropdownMenu v-if="!disabled">
                    <DropdownMenuTrigger as-child>
                      <Button variant="ghost" size="icon" :aria-label="t('Row actions')">
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem @click="openRow(item.row.__uid)">
                        <PanelRightOpen /> {{ t('Edit') }}
                      </DropdownMenuItem>
                      <DropdownMenuItem @click="table.duplicate(item.row.__uid)">
                        <Copy /> {{ t('Duplicate row') }}
                      </DropdownMenuItem>
                      <DropdownMenuItem @click="table.insert(item.row.__uid, 'above')">
                        <ArrowUp /> {{ t('Insert row above') }}
                      </DropdownMenuItem>
                      <DropdownMenuItem @click="table.insert(item.row.__uid, 'below')">
                        <ArrowDown /> {{ t('Insert row below') }}
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem variant="destructive" @click="deleteRows(table.remove(item.row.__uid))">
                        <Trash2 /> {{ t('Delete row') }}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </TableCell>
            </TableRow>
          </template>
        </VueDraggable>
      </Table>
    </div>

    <div v-if="!disabled" class="flex flex-wrap items-center gap-2">
      <template v-if="selected.size">
        <span class="text-muted-foreground">
          {{ t('Selected:') }} <span class="font-medium text-foreground tabular-nums">{{ selected.size }}</span>
        </span>
        <Button variant="outline" size="sm" @click="table.duplicateSelected()">
          <Copy /> {{ t('Duplicate') }}
        </Button>
        <Popover v-if="bulkColumns.length" v-model:open="bulkOpen">
          <PopoverTrigger as-child>
            <Button variant="outline" size="sm"><PencilLine /> {{ t('Set value') }}</Button>
          </PopoverTrigger>
          <PopoverContent align="start" class="flex w-72 flex-col gap-3">
            <Select v-model="bulkFieldname">
              <SelectTrigger class="w-full">
                <SelectValue :placeholder="t('Column')" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="f in bulkColumns" :key="f.fieldname" :value="f.fieldname">
                  {{ f.label }}
                </SelectItem>
              </SelectContent>
            </Select>
            <template v-if="bulkField">
              <Checkbox
                v-if="bulkField.fieldtype === 'Check'"
                :model-value="!!bulkValue"
                :aria-label="bulkField.label"
                @update:model-value="bulkValue = $event === true"
              />
              <component
                :is="getAsyncFieldComponent(bulkField.fieldtype)"
                v-else
                :field="bulkField"
                :model-value="bulkValue"
                @update:model-value="bulkValue = $event"
              />
            </template>
            <Button size="sm" :disabled="!bulkField" @click="applyBulk">
              {{ t('Apply to') }} {{ selected.size }}
            </Button>
          </PopoverContent>
        </Popover>
        <Button variant="outline" size="sm" class="text-destructive" @click="deleteRows(table.removeSelected())">
          <Trash2 /> {{ t('Delete') }}
        </Button>
        <Button variant="ghost" size="icon" :aria-label="t('Clear selection')" @click="table.clearSelection()">
          <X />
        </Button>
      </template>

      <template v-else>
        <Button
          variant="outline"
          size="sm"
          :disabled="!canAddRow"
          :title="canAddRow ? undefined : t('Fill in the current row first')"
          @click="addRow"
        >
          <Plus /> {{ t('Add row') }}
        </Button>
        <span v-if="invalidCount" class="inline-flex items-center gap-1 text-destructive">
          <TriangleAlert class="size-4" />
          {{ invalidCount }} {{ invalidCount === 1 ? t('row needs attention') : t('rows need attention') }}
        </span>
      </template>
    </div>

    <TableRowSheet
      :row="editingRow"
      :position="editingRow ? table.indexOf(editingRow.__uid) + 1 : 0"
      :fields="fields"
      :dynamic-field="dynamicField"
      :table-label="field.label || ''"
      :disabled="disabled"
      @close="editingUid = null"
      @save="saveRow"
      @create-new="createLinked"
    />

    <QuickEntryDialog
      v-if="quickEntry"
      :dt="quickEntry.doctype"
      :preset="quickEntry.preset"
      mode="link"
      @saved="(name: string) => { quickEntry?.apply(name); quickEntry = null }"
      @close="quickEntry = null"
    />
  </div>
</template>
