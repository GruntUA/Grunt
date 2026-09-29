<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import type { DocField, DocType, PaginationMeta } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { getListCell } from '@/core/listCellRegistry'
import { resolveStatusBadge, statusConfigOf } from '@/core/status'
import { docUrl } from '@/core/workspaceUrl'
import { useAuthStore } from '@/stores/auth'
import DefaultListCell from '@/components/fields/Default/ListCell.vue'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import ListEmptyState from '@/components/views/ListEmptyState.vue'
import { Skeleton } from '@/components/ui/skeleton'

const { t } = useI18n()

/**
 * List rows as cards — the phone-width counterpart of GruntDataTable. The first
 * list column is the card title, the DocType status is a badge, and the next few
 * columns are label / value pairs rendered by the same list-cell components the
 * table uses.
 */
const props = defineProps<{
  dt: DocType | null
  workspace: string
  doctype: string
  rows: Record<string, unknown>[]
  columns: ListColumn[]
  isLoading: boolean
  selectedIds: string[]
  allSelected?: boolean
  meta?: Pick<PaginationMeta, 'unavailable' | 'unavailable_message'>
}>()

const emit = defineEmits<{
  select: [id: string]
  rowClick: [row: Record<string, unknown>]
}>()

/** Label / value pairs under the title — more would turn a card into a form. */
const MAX_DETAILS = 4

const fieldMap = computed(() =>
  Object.fromEntries((props.dt?.fields ?? []).map((f) => [f.fieldname, f])),
)
const statusConfig = computed(() => statusConfigOf(props.dt))
const statusOf = (row: Record<string, unknown>) => resolveStatusBadge(props.dt, row)
const statusField = computed(() => props.dt?.status_field || 'status')

/** Badge-like types make a poor card title (e.g. a "Document type" Select). */
const NOT_A_TITLE = new Set(['Select', 'Check'])

/** The DocType title field if the list shows it, else the first text-like column. */
const titleColumn = computed<ListColumn | null>(() => {
  const cols = props.columns
  const titleField = props.dt?.title_field
  return (
    cols.find((c) => c.key === titleField) ??
    cols.find((c) => !NOT_A_TITLE.has(fieldMap.value[c.key]?.fieldtype ?? '')) ??
    cols[0] ??
    null
  )
})
const detailColumns = computed(() =>
  props.columns
    .filter((c) => c !== titleColumn.value && c.key !== statusField.value)
    .slice(0, MAX_DETAILS),
)

function field(col: ListColumn): DocField {
  return fieldMap.value[col.key] ?? ({ fieldname: col.key, fieldtype: 'Data', label: col.label } as DocField)
}

function cellOf(col: ListColumn) {
  return getListCell(field(col).fieldtype) ?? DefaultListCell
}

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length)
}

function rowId(row: Record<string, unknown>): string {
  return String(row.id ?? row.name ?? '')
}

function isSelected(row: Record<string, unknown>): boolean {
  return !!props.allSelected || props.selectedIds.includes(rowId(row))
}

// track_seen: `_seen` lists who opened the document — flag the unopened ones.
const auth = useAuthStore()
function isUnseen(row: Record<string, unknown>): boolean {
  return Array.isArray(row._seen) && !row._seen.includes(auth.user?.email ?? '')
}

function href(row: Record<string, unknown>): string {
  return docUrl(props.doctype, rowId(row), props.workspace)
}

// Plain click opens in-app; Ctrl/⌘/middle-click keep the browser's new-tab behaviour.
function onTitleClick(event: MouseEvent, row: Record<string, unknown>) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  emit('rowClick', row)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <template v-if="isLoading && !rows.length">
      <Card v-for="n in 4" :key="n" class="gap-3 p-4">
        <Skeleton class="h-5 w-2/3" />
        <Skeleton class="h-4 w-full" />
        <Skeleton class="h-4 w-1/2" />
      </Card>
    </template>

    <ListEmptyState v-else-if="!rows.length" class="border py-16" :meta="meta" />

    <Card
      v-for="row in rows"
      v-else
      :key="rowId(row)"
      class="cursor-pointer gap-3 p-4"
      :class="isSelected(row) && 'border-primary bg-primary/5'"
      @click="emit('rowClick', row)"
    >
      <div class="flex items-start gap-3">
        <Checkbox
          class="mt-0.5"
          :model-value="isSelected(row)"
          :aria-label="t('Select {id}', { id: String(rowId(row)) })"
          @click.stop
          @update:model-value="emit('select', rowId(row))"
        />
        <a
          :href="href(row)"
          class="min-w-0 flex-1 font-medium break-words"
          @click.stop="onTitleClick($event, row)"
        >
          <span v-if="isUnseen(row)" class="mr-1.5 inline-block size-2 rounded-full bg-primary" :aria-label="t('Unseen')" />
          <component
            :is="cellOf(titleColumn)"
            v-if="titleColumn && !isEmpty(row[titleColumn.key])"
            :value="row[titleColumn.key]"
            :row="row"
            :field="field(titleColumn)"
            :status-config="statusConfig"
          />
          <span v-else>{{ rowId(row) }}</span>
        </a>
        <Badge v-if="statusOf(row)" variant="outline" :class="statusOf(row)!.class">
          {{ statusOf(row)!.label }}
        </Badge>
      </div>

      <dl v-if="detailColumns.length" class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 pl-7">
        <template v-for="col in detailColumns" :key="col.key">
          <template v-if="!isEmpty(row[col.key])">
            <dt class="text-muted-foreground">{{ col.label }}</dt>
            <dd class="min-w-0 break-words">
              <component
                :is="cellOf(col)"
                :value="row[col.key]"
                :row="row"
                :field="field(col)"
                :status-config="statusConfig"
              />
            </dd>
          </template>
        </template>
      </dl>
    </Card>
  </div>
</template>
