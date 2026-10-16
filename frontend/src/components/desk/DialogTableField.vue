<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DialogField } from '@/core/composables/useDialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Table, TableBody, TableCell, TableEmpty, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

type Row = Record<string, unknown>

/** Selectable table inside a `form()` dialog: one row (`multiple: false`) or many. */
const props = defineProps<{
  field: DialogField
  modelValue: unknown
  busy: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [value: Row | Row[] | null]
  'row-action': [row: Row, index: number]
}>()

const { t } = useI18n()
const search = ref('')

const multiple = computed(() => props.field.multiple !== false)
const selectable = computed(() => props.field.selectable ?? multiple.value)

function keyOf(row: unknown): string {
  return String((row as Row | null)?.[props.field.rowKey || 'name'] ?? '')
}

const rows = computed(() => {
  const all = props.field.rows ?? []
  const q = search.value.toLowerCase().trim()
  if (!q) return all
  const cols = props.field.columns ?? []
  return all.filter(r => cols.some(c => String(r[c.key] ?? '').toLowerCase().includes(q)))
})

const selected = computed<Row[]>(() => {
  const v = props.modelValue
  if (Array.isArray(v)) return v
  return v ? [v as Row] : []
})
const selectedKeys = computed(() => new Set(selected.value.map(keyOf)))
const allSelected = computed(() => rows.value.length > 0 && rows.value.every(r => selectedKeys.value.has(keyOf(r))))
const colspan = computed(() =>
  (props.field.columns?.length || 1) + (selectable.value ? 1 : 0) + (props.field.rowActions?.length ? 1 : 0))

function toggleRow(row: Row) {
  const k = keyOf(row)
  const on = selectedKeys.value.has(k)
  if (!multiple.value) emit('update:modelValue', on ? null : row)
  else emit('update:modelValue', on ? selected.value.filter(r => keyOf(r) !== k) : [...selected.value, row])
}

function toggleAll() {
  const visible = new Set(rows.value.map(keyOf))
  emit('update:modelValue', allSelected.value
    ? selected.value.filter(r => !visible.has(keyOf(r)))
    : [...selected.value, ...rows.value.filter(r => !selectedKeys.value.has(keyOf(r)))])
}
</script>

<template>
  <Input v-if="field.searchable !== false" v-model="search" :placeholder="t('Search…')" />
  <div class="rounded-md border">
    <div class="overflow-auto" :style="{ maxHeight: field.maxHeight || '320px' }">
      <Table>
        <TableHeader class="bg-muted sticky top-0 z-10">
          <TableRow>
            <TableHead v-if="selectable" class="w-9">
              <Checkbox v-if="multiple" :model-value="allSelected" @update:model-value="toggleAll" />
            </TableHead>
            <TableHead
              v-for="c in field.columns"
              :key="c.key"
              :style="{ textAlign: c.align || 'left', width: c.width }"
            >{{ c.label }}</TableHead>
            <TableHead v-if="field.rowActions?.length" class="w-px" />
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="row in rows"
            :key="keyOf(row)"
            :data-state="selectedKeys.has(keyOf(row)) ? 'selected' : undefined"
            :class="selectable && 'cursor-pointer'"
            @click="selectable && toggleRow(row)"
          >
            <TableCell v-if="selectable" @click.stop>
              <Checkbox :model-value="selectedKeys.has(keyOf(row))" @update:model-value="toggleRow(row)" />
            </TableCell>
            <TableCell
              v-for="c in field.columns"
              :key="c.key"
              class="align-top whitespace-normal"
              :style="{ textAlign: c.align || 'left' }"
            >
              <span v-if="c.format" v-html="c.format(row[c.key], row)" />
              <template v-else>{{ row[c.key] ?? '—' }}</template>
            </TableCell>
            <TableCell v-if="field.rowActions?.length" class="text-right" @click.stop>
              <Button
                v-for="(act, ai) in field.rowActions"
                :key="ai"
                :variant="act.variant ?? (act.danger ? 'destructive' : 'ghost')"
                size="sm"
                :disabled="busy"
                @click="emit('row-action', row, ai)"
              >{{ act.label }}</Button>
            </TableCell>
          </TableRow>
          <TableEmpty v-if="!rows.length" :colspan="colspan" class="text-muted-foreground">
            {{ field.emptyText || t('Nothing found') }}
          </TableEmpty>
        </TableBody>
      </Table>
    </div>
    <div v-if="selectable && multiple" class="border-t bg-muted/30 px-3 py-1.5 text-muted-foreground">
      {{ t('Selected:') }} {{ selected.length }}
    </div>
  </div>
</template>
