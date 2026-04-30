<script setup lang="ts">
import { computed } from 'vue'
import type { DocType, DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import type { GroupedRowBucket } from '@/core/composables/useGrouping'
import GruntDataTable from '@/components/views/GruntDataTable.vue'
import ListPagination from '@/components/views/ListPagination.vue'
import BulkActionBar from '@/components/views/BulkActionBar.vue'
import ListGroupedView from '@/components/views/list/ListGroupedView.vue'

interface TableMeta {
  page: number
  pages: number
  total: number
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
  activeIndex: number
  groupBy: string | null
  groupedRows: GroupedRowBucket[] | null
  collapsedGroups: Set<string>
  groupByField: DocField | null
  selection: SelectionState
}>()

const emit = defineEmits<{
  'sort': [key: string]
  'row-click': [row: Record<string, unknown>]
  'inline-update': [rowId: string, field: string, value: string]
  'delete': []
  'clear': []
  'select-all': []
  'update': [field: string, value: string]
  'toggle-group': [key: string]
  'page': [page: number]
}>()

const selectionCount = computed(() => props.selection.selectedIds.length)
const normalizedSortKey = computed(() => props.sortKey || '')
</script>

<template>
  <div>
    <!-- Action Bar -->
    <BulkActionBar
      :count="selectionCount"
      :total="meta?.total"
      :all-selected="selection.allSelected"
      :page-count="rows?.length || 0"
      :editable-fields="dt?.fields"
      @delete="emit('delete')"
      @clear="emit('clear')"
      @select-all="emit('select-all')"
      @update="(field, value) => emit('update', field, value)"
    />

    <!-- List Content -->
    <div class="mt-2">
      <!-- Grouped View -->
      <ListGroupedView
        v-if="groupBy && groupedRows && dt && groupByField"
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
        @select-all="selection.toggleAll(rows?.map(r => String(r.id)) || [])"
        @row-click="(row) => emit('row-click', row)"
        @inline-update="(rowId, field, value) => emit('inline-update', rowId, field, value)"
      />

      <!-- Ungrouped List View -->
      <template v-else>
        <div class="bg-card rounded-xl shadow-md ring-1 ring-border/60 overflow-hidden">
          <GruntDataTable
            :columns="columns"
            :rows="rows"
            :fields="fields"
            :row-link-base="`/app/${workspace}/${doctype}`"
            :is-loading="isLoading"
            :sort-key="normalizedSortKey"
            :sort-order="sortOrder"
            :selected-ids="selection.selectedIds"
            :all-selected="selection.allSelected"
            :status-config="dt?.status_config"
            :active-index="activeIndex"
            @sort="(key) => emit('sort', key)"
            @select="(id) => selection.toggle(id)"
            @select-all="selection.toggleAll(rows.map(r => String(r.id)))"
            @row-click="(row) => emit('row-click', row)"
            @inline-update="(rowId, field, value) => emit('inline-update', rowId, field, value)"
          />
        </div>
        <ListPagination
          v-if="meta"
          :page="meta.page"
          :pages="meta.pages"
          :total="meta.total"
          :per-page="20"
          class="mt-4"
          @update:page="(page) => emit('page', page)"
        />
      </template>
    </div>
  </div>
</template>
