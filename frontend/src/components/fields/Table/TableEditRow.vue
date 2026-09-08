<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { GripVertical, Pencil, X, MoreVertical, Copy, ArrowUp, ArrowDown } from '@lucide/vue'
import type { DocField } from '@/types'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { TableCell, TableRow } from '@/components/ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import LinkField from '@/components/fields/Link/Link.vue'
import { INLINE_TYPES, CELL_INPUT_CLASS } from './constants'
import { useTableCell, isSubtotalRow, isLayoutRow } from './useTableCell'

const props = defineProps<{
  row: Record<string, unknown>
  columns: DocField[]
  displayIndex: number
  disabled?: boolean
  canReorder?: boolean
  selected?: boolean
  hasError?: boolean
  showEditorButton?: boolean
  /** colIdx that should show the drag-to-fill handle (this row is the active one). */
  fillHandleCol?: number | null
  /** this row is in the autofill drag range → highlight. */
  fillPreview?: boolean
}>()

const emit = defineEmits<{
  (e: 'set-cell', fieldname: string, value: unknown): void
  (e: 'create-new', doctype: string, preset: string, fieldname: string): void
  (e: 'edit'): void
  (e: 'remove'): void
  (e: 'duplicate'): void
  (e: 'insert-above'): void
  (e: 'insert-below'): void
  (e: 'toggle-select'): void
  (e: 'cell-keydown', ev: KeyboardEvent, colIdx: number): void
  (e: 'cell-focus', colIdx: number): void
  (e: 'fill-start', colIdx: number): void
}>()

const { t } = useI18n()
const cell = useTableCell(() => props.columns)

const isSubtotal = computed(() => isSubtotalRow(props.row))
const isLayoutRowV = computed(() => isLayoutRow(props.row))

const cellError = (f: DocField) => cell.cellError(props.row, f)
const cellDisplay = (f: DocField) => cell.cellDisplay(props.row, f)
const subtotalDisplay = (f: DocField) => cell.subtotalCellDisplay(props.row, f)
const selectOptions = cell.selectOptions

function isInline(f: DocField): boolean {
  return !props.disabled && !isLayoutRowV.value && !f.read_only && INLINE_TYPES.has(f.fieldtype)
}
</script>

<template>
  <TableRow
    :class="[
      isSubtotal && 'bg-muted/40 border-t border-border font-semibold',
      isLayoutRowV && 'text-muted-foreground/70',
      hasError && 'shadow-[inset_2px_0_0_0_hsl(var(--destructive))]',
      fillPreview && 'bg-primary/10',
    ]"
    :data-state="!isSubtotal && selected ? 'selected' : undefined"
    class="group/row"
  >
    <TableCell class="text-center align-middle sticky left-0 z-10 bg-card" @click.stop>
      <Checkbox
        v-if="!isSubtotal"
        :model-value="!!selected"
        :aria-label="t('Select row')"
        @update:model-value="emit('toggle-select')"
      />
    </TableCell>

    <TableCell
      class="text-center text-xs text-muted-foreground select-none align-middle sticky left-10 z-10 bg-card border-r border-border"
      :class="canReorder && !isSubtotal && 'row-drag-handle cursor-grab active:cursor-grabbing'"
    >
      <span v-if="!isSubtotal" class="inline-flex items-center gap-1">
        <GripVertical
          v-if="canReorder"
          class="size-3 text-muted-foreground/30 group-hover/row:text-muted-foreground/70 transition-colors"
        />
        {{ displayIndex }}
      </span>
    </TableCell>

    <TableCell
      v-for="(f, colIdx) in columns"
      :key="f.fieldname"
      :data-cell="`${row.__uid}:${colIdx}`"
      class="p-0 align-middle relative"
      @focusin="emit('cell-focus', colIdx)"
    >
      <!-- Autofill handle (bottom-right of the active cell) -->
      <span
        v-if="fillHandleCol === colIdx && !disabled && !isSubtotal && !isLayoutRowV"
        class="absolute -bottom-[3px] -right-[3px] z-10 size-2 rounded-[1px] bg-primary ring-1 ring-background cursor-crosshair"
        :title="t('Drag to fill down')"
        @mousedown.stop.prevent="emit('fill-start', colIdx)"
      />

      <!-- Subtotal -->
      <span v-if="isSubtotal" class="block px-3 py-2 text-xs font-semibold text-foreground">
        {{ subtotalDisplay(f) }}
      </span>

      <!-- Read-only / non-inline -->
      <span
        v-else-if="!isInline(f)"
        :class="['block px-3 py-2 text-xs break-words whitespace-pre-wrap', !cellDisplay(f) && 'text-muted-foreground/60']"
      >
        {{ cellDisplay(f) || '—' }}
      </span>

      <!-- Check -->
      <div v-else-if="f.fieldtype === 'Check'" class="flex justify-center py-2">
        <Checkbox
          :model-value="Boolean(row[f.fieldname])"
          :aria-label="f.label"
          @update:model-value="emit('set-cell', f.fieldname, $event === true)"
        />
      </div>

      <!-- Link -->
      <div v-else-if="f.fieldtype === 'Link'" :title="cellError(f) || undefined">
        <LinkField
          cell
          :field="f"
          :model-value="row[f.fieldname] ?? null"
          :doc="row"
          :error="cellError(f) || undefined"
          @update:model-value="emit('set-cell', f.fieldname, $event)"
          @create-new="(dt, preset) => emit('create-new', dt, preset, f.fieldname)"
        />
      </div>

      <!-- Select -->
      <select
        v-else-if="f.fieldtype === 'Select'"
        :value="String(row[f.fieldname] ?? '')"
        :aria-label="f.label"
        :aria-invalid="!!cellError(f)"
        :title="cellError(f) || undefined"
        :class="[CELL_INPUT_CLASS, 'border appearance-none text-foreground outline-none aria-invalid:border-destructive aria-invalid:ring-1 aria-invalid:ring-destructive/30 [&>option]:bg-popover [&>option]:text-popover-foreground']"
        @change="emit('set-cell', f.fieldname, ($event.target as HTMLSelectElement).value)"
        @keydown="emit('cell-keydown', $event, colIdx)"
      >
        <option v-if="!f.required" value="">—</option>
        <option v-for="opt in selectOptions(f)" :key="opt" :value="opt">{{ opt }}</option>
      </select>

      <!-- Int / Float -->
      <Input
        v-else-if="f.fieldtype === 'Int' || f.fieldtype === 'Float'"
        type="number"
        :model-value="(row[f.fieldname] ?? '') as string | number"
        :step="f.fieldtype === 'Float' ? 'any' : '1'"
        :placeholder="f.placeholder || ''"
        :aria-label="f.label"
        :aria-invalid="!!cellError(f)"
        :title="cellError(f) || undefined"
        :class="CELL_INPUT_CLASS"
        @update:model-value="emit('set-cell', f.fieldname, $event === '' || $event == null ? null : Number($event))"
        @keydown="emit('cell-keydown', $event, colIdx)"
      />

      <!-- Date / Datetime / Time -->
      <Input
        v-else-if="['Date', 'Datetime', 'Time'].includes(f.fieldtype)"
        :type="f.fieldtype === 'Date' ? 'date' : f.fieldtype === 'Datetime' ? 'datetime-local' : 'time'"
        :model-value="String(row[f.fieldname] ?? '')"
        :aria-label="f.label"
        :aria-invalid="!!cellError(f)"
        :title="cellError(f) || undefined"
        :class="CELL_INPUT_CLASS"
        @update:model-value="emit('set-cell', f.fieldname, $event)"
        @keydown="emit('cell-keydown', $event, colIdx)"
      />

      <!-- Text -->
      <Input
        v-else
        type="text"
        :model-value="String(row[f.fieldname] ?? '')"
        :placeholder="f.placeholder || ''"
        :aria-label="f.label"
        :aria-invalid="!!cellError(f)"
        :title="cellError(f) || undefined"
        :class="CELL_INPUT_CLASS"
        @update:model-value="emit('set-cell', f.fieldname, $event)"
        @keydown="emit('cell-keydown', $event, colIdx)"
      />
    </TableCell>

    <TableCell class="align-middle">
      <div class="flex items-center justify-end gap-0.5">
        <button
          v-if="showEditorButton && !isSubtotal"
          type="button"
          class="p-1 rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
          :title="disabled ? t('View') : t('Edit')"
          :aria-label="disabled ? t('View') : t('Edit')"
          @click="emit('edit')"
        >
          <Pencil class="size-3.5" />
        </button>

        <DropdownMenu v-if="!disabled && !isSubtotal">
          <DropdownMenuTrigger as-child>
            <button
              type="button"
              class="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              :title="t('Row actions')"
              :aria-label="t('Row actions')"
            >
              <MoreVertical class="size-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-44">
            <DropdownMenuItem @click="emit('duplicate')">
              <Copy class="size-3.5" /> {{ t('Duplicate row') }}
            </DropdownMenuItem>
            <DropdownMenuItem @click="emit('insert-above')">
              <ArrowUp class="size-3.5" /> {{ t('Insert row above') }}
            </DropdownMenuItem>
            <DropdownMenuItem @click="emit('insert-below')">
              <ArrowDown class="size-3.5" /> {{ t('Insert row below') }}
            </DropdownMenuItem>
            <DropdownMenuItem class="text-destructive" @click="emit('remove')">
              <X class="size-3.5" /> {{ t('Delete row') }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </TableCell>
  </TableRow>
</template>
