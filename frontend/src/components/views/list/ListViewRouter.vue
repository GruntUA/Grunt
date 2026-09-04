<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { getViewDef, type ViewContext, type SelectionState } from '@/core/viewRegistry'
import type { DocType, DocField, ActiveFilter, QuickFilter, ScriptMenuItem } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import type { GroupedRowBucket } from '@/core/composables/useGrouping'

interface TableMeta {
  page: number
  pages: number
  total: number
}

const props = defineProps<{
  viewMode: string
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
  fetchNextPage?: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  search?: string
  activeFilters: ActiveFilter[]
  quickFilterDefs: QuickFilter[]
  quickFilterValues: Record<string, string>
  isSuperadmin?: boolean
  refreshKey: number
}>()

const emit = defineEmits<{
  sort: [key: string]
  'row-click': [row: Record<string, unknown>]
  'inline-update': [rowId: string, field: string, value: string]
  delete: []
  'fast-delete': []
  clear: []
  'select-all': []
  update: [field: string, value: unknown]
  'toggle-group': [key: string]
  page: [page: number]
  'register-menu-items': [items: ScriptMenuItem[]]
  'unregister-menu-items': [items: ScriptMenuItem[]]
  'update:quickFilterValues': [val: Record<string, string>]
  'update:activeFilters': [val: ActiveFilter[]]
}>()

const viewDef = computed(() => getViewDef(props.viewMode))

const resolvedField = computed((): DocField | null => {
  const def = viewDef.value
  if (!def?.resolveField || !props.dt) return null
  return def.resolveField(props.dt)
})

const isRenderable = computed(() => {
  const def = viewDef.value
  if (!def) return false
  if (!def.resolveField) return true
  return resolvedField.value !== null
})

const ctx = computed((): ViewContext => ({
  dt: props.dt,
  workspace: props.workspace,
  doctype: props.doctype,
  rows: props.rows,
  fields: props.fields,
  columns: props.columns,
  meta: props.meta,
  isLoading: props.isLoading,
  hasData: props.hasData,
  selectionCount: props.selectionCount,
  selection: props.selection,
  imageField: props.imageField,
  groupBy: props.groupBy,
  groupedRows: props.groupedRows,
  collapsedGroups: props.collapsedGroups,
  groupByField: props.groupByField,
  sortKey: props.sortKey,
  sortOrder: props.sortOrder,
  fetchNextPage: props.fetchNextPage,
  hasNextPage: props.hasNextPage,
  isFetchingNextPage: props.isFetchingNextPage,
  search: props.search,
  activeFilters: props.activeFilters,
  quickFilterDefs: props.quickFilterDefs,
  quickFilterValues: props.quickFilterValues,
  resolvedField: resolvedField.value,
  isSuperadmin: props.isSuperadmin,
  refreshKey: props.refreshKey,
  emit: {
    sort: (key) => emit('sort', key),
    rowClick: (row) => emit('row-click', row),
    inlineUpdate: (id, field, value) => emit('inline-update', id, field, value),
    delete: () => emit('delete'),
    fastDelete: () => emit('fast-delete'),
    clear: () => emit('clear'),
    selectAll: () => emit('select-all'),
    update: (field, value) => emit('update', field, value),
    toggleGroup: (key) => emit('toggle-group', key),
    page: (p) => emit('page', p),
    registerMenuItems: (items) => emit('register-menu-items', items),
    unregisterMenuItems: (items) => emit('unregister-menu-items', items),
    updateQuickFilterValues: (val) => emit('update:quickFilterValues', val),
    updateActiveFilters: (val) => emit('update:activeFilters', val),
  },
}))

// defineAsyncComponent is recreated on viewMode change; Vite caches the import promise
const viewComponent = computed(() => {
  const def = viewDef.value
  return def ? defineAsyncComponent(def.component) : null
})

const viewProps = computed(() => viewDef.value?.mountProps?.(ctx.value) ?? {})
const viewEvents = computed(() => viewDef.value?.mountEvents?.(ctx.value) ?? {})
</script>

<template>
  <div class="flex-1 min-h-0">
    <component
      :is="viewComponent"
      v-if="isRenderable && viewComponent"
      v-bind="{ ...viewProps, ...viewEvents }"
    />
  </div>
</template>
