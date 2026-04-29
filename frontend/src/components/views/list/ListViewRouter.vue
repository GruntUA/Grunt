<script setup lang="ts">
import type { DocType, DocField, ScriptMenuItem, ActiveFilter, FastFilter } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import type { GroupedRowBucket } from '@/core/composables/useGrouping'
import KanbanView from '@/components/views/KanbanView.vue'
import CalendarView from '@/components/views/CalendarView.vue'
import TreeView from '@/components/views/TreeView.vue'
import GalleryView from '@/components/views/GalleryView.vue'
import MapView from '@/components/views/MapView.vue'
import BulkActionBar from '@/components/views/BulkActionBar.vue'
import ListPagination from '@/components/views/ListPagination.vue'
import ListTableView from '@/components/views/list/ListTableView.vue'

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
  viewMode: 'list' | 'kanban' | 'calendar' | 'tree' | 'gallery' | 'map'
  dt: DocType | null
  workspace: string
  doctype: string
  rows: Record<string, unknown>[]
  fields: DocField[]
  columns: ListColumn[]
  meta?: TableMeta
  isLoading: boolean
  hasData: boolean
  selectionCount: number
  selection: SelectionState
  imageField?: string
  groupBy: string | null
  groupedRows: GroupedRowBucket[] | null
  collapsedGroups: Set<string>
  groupByField: DocField | null
  sortKey: string | null
  sortOrder: 'asc' | 'desc'
  activeIndex: number
  kanbanColumnField: DocField | null
  calendarDateField: DocField | null
  treeParentField: DocField | null
  geoField: DocField | null
  search?: string
  activeFilters: ActiveFilter[]
  fastFilterDefs: FastFilter[]
  fastFilterValues: Record<string, string>
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
  'register-menu-items': [items: ScriptMenuItem[]]
  'unregister-menu-items': [items: ScriptMenuItem[]]
  'update:fastFilterValues': [val: Record<string, string>]
  'update:activeFilters': [val: ActiveFilter[]]
}>()
</script>

<template>
  <div class="flex-1 min-h-0">
    <div v-if="viewMode === 'kanban' && kanbanColumnField && dt" class="h-[calc(100vh-14rem)]">
      <KanbanView :doctype="dt" :column-field="kanbanColumnField.fieldname" />
    </div>

    <div v-else-if="viewMode === 'calendar' && calendarDateField && dt" class="h-[calc(100vh-14rem)]">
      <CalendarView :doctype="dt" :date-field="calendarDateField.fieldname" :workspace="workspace" />
    </div>

    <div v-else-if="viewMode === 'tree' && treeParentField && dt">
      <TreeView :doctype="dt" :parent-field="treeParentField.fieldname" :workspace="workspace"
        :fast-filter-defs="fastFilterDefs" :fast-filter-values="fastFilterValues" :active-filters="activeFilters"
        @update:fast-filter-values="emit('update:fastFilterValues', $event)"
        @update:active-filters="emit('update:activeFilters', $event)" />
    </div>

    <div v-else-if="viewMode === 'map' && geoField && dt">
      <MapView :doctype="dt" :geo-field="geoField.fieldname" :workspace="workspace" :search="search"
        :filters="activeFilters" @register-menu-items="(items) => emit('register-menu-items', items)"
        @unregister-menu-items="(items) => emit('unregister-menu-items', items)" />
    </div>

    <div v-else-if="viewMode === 'gallery'">
      <BulkActionBar :count="selectionCount" :total="meta?.total" :all-selected="selection.allSelected"
        :page-count="rows?.length || 0" :editable-fields="dt?.fields" @delete="emit('delete')" @clear="emit('clear')"
        @select-all="emit('select-all')" @update="(field, value) => emit('update', field, value)" />
      <GalleryView :rows="rows" :columns="columns" :fields="fields" :doctype="doctype" :image-field="imageField"
        :workspace="workspace" :is-loading="isLoading && !hasData"
        :selection="{ selectedIds: selection.selectedIds, allSelected: selection.allSelected, isSelected: selection.isSelected, toggle: selection.toggle }" />
      <ListPagination v-if="meta" :page="meta.page" :pages="meta.pages" :total="meta.total" :per-page="20"
        @update:page="(page) => emit('page', page)" />
    </div>

    <template v-else>
      <ListTableView :dt="dt" :rows="rows" :columns="columns" :fields="fields" :meta="meta"
        :is-loading="isLoading && !hasData" :sort-key="sortKey" :sort-order="sortOrder" :active-index="activeIndex"
        :group-by="groupBy" :grouped-rows="groupedRows" :collapsed-groups="collapsedGroups"
        :group-by-field="groupByField" :selection="selection" @sort="(key) => emit('sort', key)"
        @row-click="(row) => emit('row-click', row)"
        @inline-update="(rowId, field, value) => emit('inline-update', rowId, field, value)" @delete="emit('delete')"
        @clear="emit('clear')" @select-all="emit('select-all')" @update="(field, value) => emit('update', field, value)"
        @toggle-group="(k) => emit('toggle-group', k)" @page="(page) => emit('page', page)" />
    </template>
  </div>
</template>
