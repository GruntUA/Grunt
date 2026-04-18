<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'
import type { DocField, DocType } from '@/types'
import { metaApi } from '@/core/api'
import { Plus, X, Pencil, GripVertical } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import FieldRenderer from '@/core/renderer/FieldRenderer.vue'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import { getLayoutTypeSet } from '@/core/fieldRegistry'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  'create-new': [doctype: string, preset: string, fieldname: string]
}>()

// ── State ─────────────────────────────────────────────────────────────────────

const { t } = useI18n()
const childDocType = ref<DocType | null>(null)
const rows = ref<Record<string, unknown>[]>([])
const loading = ref(false)

const editIdx = ref<number | null>(null)
const editDraft = ref<Record<string, unknown>>({})

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

function onDragEnd() {
  emit('update:modelValue', [...rows.value])
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

// Display value for non-editable cells (complex types or disabled mode)
function cellDisplay(row: Record<string, unknown>, f: DocField): string {
  const val = row[f.fieldname]
  if (val === null || val === undefined || val === '') return ''
  if (f.fieldtype === 'Check') return val ? t('Yes') : t('No')
  const str = f.fieldtype === 'Link'
    ? String(row[`${f.fieldname}__label`] ?? val)
    : String(val)
  return str.length > 40 ? str.slice(0, 40) + '…' : str
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="border border-border rounded-lg overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-muted/60">
          <tr>
            <!-- Drag handle spacer -->
            <th v-if="!disabled" class="w-7 border-b border-border" />
            <th class="w-8 px-3 py-2 text-xs font-medium text-muted-foreground border-b border-border text-center">#</th>
            <th
              v-for="f in tableColumns"
              :key="f.fieldname"
              :class="['text-left px-3 py-2 text-xs font-medium text-muted-foreground border-b border-border', colClass(f)]"
            >
              {{ f.label }}<span v-if="f.required" class="text-destructive ml-0.5">*</span>
            </th>
            <th class="w-20 border-b border-border" />
          </tr>
        </thead>

        <!-- Draggable tbody -->
        <draggable
          v-model="rows"
          tag="tbody"
          item-key="__idx"
          handle=".drag-handle"
          :disabled="disabled"
          @end="onDragEnd"
        >
          <template #item="{ element: row, index: i }">
            <tr class="border-b border-border last:border-0 hover:bg-muted/30 transition-colors group">
              <!-- Drag handle -->
              <td v-if="!disabled" class="pl-2 py-1 text-center">
                <GripVertical class="drag-handle size-4 text-muted-foreground/40 hover:text-muted-foreground cursor-grab active:cursor-grabbing transition-colors" />
              </td>

              <!-- Row number -->
              <td class="px-3 py-1.5 text-center text-xs text-muted-foreground select-none">{{ i + 1 }}</td>

              <!-- Cells -->
              <td v-for="(f, colIdx) in tableColumns" :key="f.fieldname" :class="['px-2 py-1', colClass(f)]">

                <!-- Disabled or complex type → plain text -->
                <template v-if="disabled || !INLINE_TYPES.has(f.fieldtype)">
                  <span
                    :class="['block px-2 py-1 text-sm truncate', !cellDisplay(row, f) && 'text-muted-foreground/40']"
                    :title="String(row[f.fieldname] ?? '')"
                  >
                    {{ cellDisplay(row, f) || '—' }}
                  </span>
                </template>

                <!-- Check -->
                <template v-else-if="f.fieldtype === 'Check'">
                  <div class="flex justify-center">
                    <input
                      type="checkbox"
                      :checked="Boolean(row[f.fieldname])"
                      class="rounded border-border size-4"
                      @change="updateCell(i, f.fieldname, ($event.target as HTMLInputElement).checked)"
                    />
                  </div>
                </template>

                <!-- Select -->
                <template v-else-if="f.fieldtype === 'Select'">
                  <select
                    :value="String(row[f.fieldname] ?? '')"
                    class="w-full px-2 py-1 text-sm border border-transparent rounded-md bg-transparent hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                    @change="updateCell(i, f.fieldname, ($event.target as HTMLSelectElement).value)"
                    @keydown="onCellKeydown($event, i, colIdx)"
                  >
                    <option value="">—</option>
                    <option v-for="opt in selectOptions(f)" :key="opt" :value="opt">{{ opt }}</option>
                  </select>
                </template>

                <!-- Int / Float -->
                <template v-else-if="f.fieldtype === 'Int' || f.fieldtype === 'Float'">
                  <input
                    type="number"
                    :value="row[f.fieldname] ?? ''"
                    :step="f.fieldtype === 'Float' ? 'any' : '1'"
                    class="w-full px-2 py-1 text-sm border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                    @input="updateCell(i, f.fieldname, Number(($event.target as HTMLInputElement).value))"
                    @keydown="onCellKeydown($event, i, colIdx)"
                  />
                </template>

                <!-- Date / Datetime / Time -->
                <template v-else-if="['Date', 'Datetime', 'Time'].includes(f.fieldtype)">
                  <input
                    :type="f.fieldtype === 'Date' ? 'date' : f.fieldtype === 'Datetime' ? 'datetime-local' : 'time'"
                    :value="String(row[f.fieldname] ?? '')"
                    class="w-full px-2 py-1 text-sm border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                    @input="updateCell(i, f.fieldname, ($event.target as HTMLInputElement).value)"
                    @keydown="onCellKeydown($event, i, colIdx)"
                  />
                </template>

                <!-- Text -->
                <template v-else>
                  <input
                    type="text"
                    :value="String(row[f.fieldname] ?? '')"
                    class="w-full px-2 py-1 text-sm border border-transparent rounded-md hover:border-border focus:border-ring focus:ring-1 focus:ring-ring focus:outline-none"
                    @input="updateCell(i, f.fieldname, ($event.target as HTMLInputElement).value)"
                    @keydown="onCellKeydown($event, i, colIdx)"
                  />
                </template>
              </td>

              <!-- Row actions -->
              <td class="px-2 py-1">
                <div class="flex items-center justify-end gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    v-if="allFields.length"
                    type="button"
                    class="p-1 rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                    :title="disabled ? t('View') : t('Edit')"
                    @click="openEditor(i)"
                  >
                    <Pencil class="size-3.5" />
                  </button>
                  <button
                    v-if="!disabled"
                    type="button"
                    class="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                    :title="t('Delete row')"
                    @click="removeRow(i)"
                  >
                    <X class="size-3.5" />
                  </button>
                </div>
              </td>
            </tr>
          </template>

          <!-- Empty state (slot required by draggable) -->
          <template #footer>
            <tr v-if="!rows.length">
              <td :colspan="tableColumns.length + (disabled ? 2 : 3)" class="px-3 py-8 text-center text-muted-foreground text-sm">
                <span v-if="loading">{{ t('Loading...') }}</span>
                <span v-else>{{ t('No rows') }}</span>
              </td>
            </tr>
          </template>
        </draggable>
      </table>
    </div>

    <!-- Add row -->
    <Button
      v-if="!disabled"
      type="button"
      variant="ghost"
      size="sm"
      class="self-start text-primary"
      @click="addRow"
    >
      <Plus class="size-4 mr-1" />
      {{ t('Add row') }}
    </Button>

    <!-- Row edit dialog -->
    <Dialog :open="editIdx !== null" @update:open="(v) => { if (!v) editIdx = null }">
      <DialogContent class="max-w-xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {{ field.label }} — рядок {{ editIdx !== null ? editIdx + 1 : '' }}
          </DialogTitle>
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
</template>
