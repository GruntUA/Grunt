<script setup lang="ts">
import { computed } from 'vue'
import type { DocType, DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import type { GroupedRowBucket } from '@/core/composables/useGrouping'
import GruntDataTable from '@/components/views/GruntDataTable.vue'
import BulkActionBar from '@/components/views/BulkActionBar.vue'
import ListGroupedView from '@/components/views/list/ListGroupedView.vue'
import ListCards from '@/components/views/list/ListCards.vue'
import { useCardLayout } from '@/components/views/list/useCardLayout'
import { statusConfigOf } from '@/core/status'
import { docUrl } from '@/core/workspaceUrl'

interface TableMeta {
  page: number
  pages: number
  total: number
  unavailable?: boolean
  unavailable_message?: string
}

interface SelectionState {
  selectedIds: string[]
  allSelected: boolean
  isSelected: (id: string) => boolean
  toggle: (id: string) => void
  toggleAll: (ids: string[]) => void
}

const props = defineProps<{
  dt: DocType | null
  workspace: string
  doctype: string
  rows: Record<string, unknown>[]
  columns: ListColumn[]
  fields: DocField[]
  meta: TableMeta | undefined
  isLoading: boolean
  sortKey: string | null
  sortOrder: 'asc' | 'desc'
  groupBy: string | null
  groupedRows: GroupedRowBucket[] | null
  collapsedGroups: Set<string>
  groupByField: DocField | null
  selection: SelectionState
  isSystemManager?: boolean
}>()

const emit = defineEmits<{
  'sort': [key: string]
  'row-click': [row: Record<string, unknown>]
  'inline-update': [rowId: string, field: string, value: string]
  'delete': [replaceWith?: string]
  'fast-delete': []
  'clear': []
  'select-all': []
  'update': [field: string, value: unknown]
  'toggle-group': [key: string]
}>()

const cardLayout = useCardLayout()
const selectionCount = computed(() => props.selection.selectedIds.length)
const normalizedSortKey = computed(() => props.sortKey || '')

function rowDocId(row: Record<string, unknown>): string {
  return String(row.id ?? row.name ?? '')
}
</script>

<template>
  <!-- Bounded to the page height: rows scroll here, header/toolbar/pager stay put. -->
  <div class="flex h-full min-h-0 flex-col">
    <!-- Action Bar -->
    <BulkActionBar
      :count="selectionCount"
      :total="meta?.total"
      :all-selected="selection.allSelected"
      :page-count="rows?.length || 0"
      :editable-fields="dt?.fields"
      :doctype="doctype"
      :selected-ids="selection.selectedIds"
      @delete="(rw) => emit('delete', rw)"
      @fast-delete="emit('fast-delete')"
      @clear="emit('clear')"
      @select-all="emit('select-all')"
      @update="(field, value) => emit('update', field, value)"
    />

    <!-- List Content -->
    <div class="flex min-h-0 flex-1 flex-col">
      <!-- Grouped View -->
      <ListGroupedView
        v-if="groupBy && groupedRows && dt && groupByField"
        class="min-h-0 overflow-y-auto"
        :dt="dt"
        :workspace="workspace"
        :doctype="doctype"
        :grouped-rows="groupedRows"
        :columns="columns"
        :collapsed-groups="collapsedGroups"
        :sort-key="normalizedSortKey"
        :sort-order="sortOrder"
        :selection="selection"
        :group-by-field="groupByField"
        @toggle-group="(k) => emit('toggle-group', k)"
        @sort="(key) => emit('sort', key)"
        @select-all="selection.toggleAll(rows?.map((r) => rowDocId(r)).filter(Boolean) || [])"
        @row-click="(row) => emit('row-click', row)"
        @inline-update="(rowId, field, value) => emit('inline-update', rowId, field, value)"
      />

      <!-- Phone width: cards instead of a table -->
      <ListCards
        v-else-if="cardLayout"
        class="min-h-0 overflow-y-auto"
        :dt="dt"
        :workspace="workspace"
        :doctype="doctype"
        :rows="rows"
        :columns="columns"
        :is-loading="isLoading"
        :selected-ids="selection.selectedIds"
        :all-selected="selection.allSelected"
        :meta="meta"
        @select="(id) => selection.toggle(id)"
        @row-click="(row) => emit('row-click', row)"
      />

      <!-- Ungrouped List View -->
      <template v-else>
        <!-- The card is the scroller (both axes) so the column header can stick to its top. -->
        <div
          class="bg-card rounded-lg ring-1 ring-border/60 min-h-0 overflow-auto [&_[data-slot=table-container]]:overflow-visible [&_thead]:sticky [&_thead]:top-0 [&_thead]:z-10 [&_thead]:bg-card"
        >
          <GruntDataTable
            :columns="columns"
            :rows="rows"
            :fields="fields"
            :meta="meta"
            :row-link-base="docUrl(doctype, null, workspace)"
            :doctype="doctype"
            :is-loading="isLoading"
            :sort-key="normalizedSortKey"
            :sort-order="sortOrder"
            :selected-ids="selection.selectedIds"
            :all-selected="selection.allSelected"
            :status-config="statusConfigOf(dt)"
            @sort="(key) => emit('sort', key)"
            @select="(id) => selection.toggle(id)"
            @select-all="selection.toggleAll(rows.map((r) => rowDocId(r)).filter(Boolean))"
            @row-click="(row) => emit('row-click', row)"
            @inline-update="(rowId, field, value) => emit('inline-update', rowId, field, value)"
          />
        </div>
      </template>
    </div>
  </div>
</template>
