<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useDocTypeStore } from '@/stores/doctype'
import { useListSelection } from '@/core/composables/useListSelection'
import { useListColumns } from '@/core/composables/useListColumns'
import { docsApi } from '@/core/api/docs'
import type { DocType, DocField } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Download, Plus } from 'lucide-vue-next'
import ViewToggle from '@/components/views/ViewToggle.vue'
import type { ViewMode } from '@/components/views/ViewToggle.vue'
import SearchToolbar from '@/components/views/SearchToolbar.vue'
import FilterBar from '@/components/views/FilterBar.vue'
import BulkActionBar from '@/components/views/BulkActionBar.vue'
import DataTable from '@/components/views/DataTable.vue'
import ListPagination from '@/components/views/ListPagination.vue'
import KanbanView from '@/components/views/KanbanView.vue'
import CalendarView from '@/components/views/CalendarView.vue'
import TreeView from '@/components/views/TreeView.vue'

const props = defineProps<{ doctype: string; workspace?: string }>()
const router = useRouter()
const dtStore = useDocTypeStore()
const queryClient = useQueryClient()

const dt = ref<DocType | null>(null)
const page = ref(1)
const debouncedSearch = ref('')
const sortKey = ref('')
const sortOrder = ref<'asc' | 'desc'>('asc')
const activeFilters = ref<Record<string, string>>({})
const viewMode = ref<ViewMode>('list')

const selection = useListSelection()
const columns = useListColumns(props.doctype, () => dt.value?.fields ?? [])

onMounted(async () => { dt.value = await dtStore.get(props.doctype) })

// ── View mode detection ──────────────────────────────────────────────

const kanbanColumnField = computed<DocField | null>(() => {
  if (!dt.value) return null
  return dt.value.fields.find(
    (f: DocField) => f.fieldtype === 'Select' && f.in_list_view && !f.hidden,
  ) ?? null
})

const treeParentField = computed<DocField | null>(() => {
  if (!dt.value) return null
  if (dt.value.tree_view?.parent_field) {
    return dt.value.fields.find(f => f.fieldname === dt.value!.tree_view!.parent_field) ?? null
  }
  return dt.value.fields.find(
    f => f.fieldtype === 'Link' && f.options === dt.value!.name,
  ) ?? null
})

const calendarDateField = computed<DocField | null>(() => {
  if (!dt.value) return null
  if (dt.value.calendar_view?.field) {
    return dt.value.fields.find(f => f.fieldname === dt.value!.calendar_view!.field) ?? null
  }
  return dt.value.fields.find(f => f.fieldtype === 'Date' || f.fieldtype === 'Datetime') ?? null
})

const hasViewToggle = computed(() => !!(kanbanColumnField.value || treeParentField.value))

// ── Data fetching ────────────────────────────────────────────────────

const { data, isLoading } = useQuery({
  queryKey: computed(() => [
    'documents', props.doctype, page.value, debouncedSearch.value,
    sortKey.value, sortOrder.value, JSON.stringify(activeFilters.value),
  ]),
  queryFn: () => docsApi.list(props.doctype, {
    page: page.value,
    per_page: 20,
    search: debouncedSearch.value || undefined,
    sort: sortKey.value || undefined,
    order: sortKey.value ? sortOrder.value : undefined,
    filters: activeFilters.value,
  }),
})

const meta = computed(() => data.value?.meta)
const rows = computed(() => (data.value?.data ?? []) as Record<string, unknown>[])

// ── Event handlers ───────────────────────────────────────────────────

function onSearch(val: string) {
  debouncedSearch.value = val
  page.value = 1
}

function onSort(key: string) {
  sortOrder.value = sortKey.value === key && sortOrder.value === 'asc' ? 'desc' : 'asc'
  sortKey.value = key
}

function onFiltersChange(f: Record<string, string>) {
  activeFilters.value = f
  page.value = 1
}

function onSelectAll() {
  const allIds = rows.value.map(r => String(r.id))
  selection.toggleAll(allIds)
}

async function bulkDelete() {
  if (selection.allSelected.value) {
    // Fetch ALL document IDs matching current filters
    const all = await docsApi.list(props.doctype, {
      page: 1,
      per_page: 200,
      search: debouncedSearch.value || undefined,
      fields: 'id',
      filters: activeFilters.value,
    })
    const allIds = ((all.data ?? []) as Record<string, unknown>[]).map(r => String(r.id))
    if (allIds.length) {
      await docsApi.bulkDelete(props.doctype, allIds)
    }
  } else {
    await docsApi.bulkDelete(props.doctype, selection.selectedIds.value)
  }
  selection.clear()
  queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
}

const isSystemDocType = computed(() => props.doctype === 'DocType')

function navigateToDoc(row: Record<string, unknown>) {
  const ws = props.workspace ?? 'grunt'
  if (isSystemDocType.value) {
    router.push(`/${ws}/list/DocType/${row.name}`)
  } else {
    router.push(`/${ws}/list/${props.doctype}/${row.id}`)
  }
}
</script>

<template>
  <div class="p-6 lg:p-8">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-3">
        <h1 class="text-xl font-semibold text-foreground">{{ dt?.label ?? doctype }}</h1>
        <Badge v-if="meta" variant="secondary" class="font-normal">{{ meta.total }}</Badge>
      </div>
      <div class="flex items-center gap-2">
        <ViewToggle
          v-if="hasViewToggle"
          v-model="viewMode"
          :has-kanban="!!kanbanColumnField"
          :has-calendar="!!calendarDateField"
          :has-tree="!!treeParentField"
        />
        <Button v-if="!isSystemDocType" variant="outline" size="sm" as="a" :href="`/api/v1/docs/${doctype}/export/xlsx`" download>
          <Download class="size-4 mr-1.5" />
          Excel
        </Button>
        <Button v-if="isSystemDocType" size="sm" @click="router.push('/studio')">
          <Plus class="size-4 mr-1.5" />
          Новий DocType
        </Button>
        <Button v-else size="sm" @click="router.push(workspace ? `/${workspace}/list/${doctype}/new` : `/${doctype}/new`)">
          <Plus class="size-4 mr-1.5" />
          Новий
        </Button>
      </div>
    </div>

    <!-- Alternate views -->
    <div v-if="viewMode === 'kanban' && kanbanColumnField && dt" class="h-[calc(100vh-12rem)]">
      <KanbanView :doctype="dt" :column-field="kanbanColumnField.fieldname" />
    </div>
    <div v-else-if="viewMode === 'calendar' && calendarDateField && dt" class="h-[calc(100vh-12rem)]">
      <CalendarView :doctype="dt" :date-field="calendarDateField.fieldname" :workspace="workspace" />
    </div>
    <div v-else-if="viewMode === 'tree' && treeParentField && dt">
      <TreeView :doctype="dt" :parent-field="treeParentField.fieldname" :workspace="workspace" />
    </div>

    <!-- List view -->
    <template v-else>
      <SearchToolbar
        :all-columns="columns.allColumns.value"
        :hidden-cols="columns.hiddenCols.value"
        @search="onSearch"
        @toggle-col="columns.toggleCol"
      />

      <FilterBar v-if="dt" :fields="dt.fields" @change="onFiltersChange" />

      <BulkActionBar
        :count="selection.allSelected.value ? (meta?.total ?? 0) : selection.selectedIds.value.length"
        :total="meta?.total"
        :all-selected="selection.allSelected.value"
        :page-count="rows.length"
        @delete="bulkDelete"
        @clear="selection.clear"
        @select-all="selection.selectAllDocuments"
      />

      <DataTable
        :columns="columns.visibleColumns.value"
        :rows="rows"
        :fields="dt?.fields ?? []"
        :is-loading="isLoading && !data"
        :sort-key="sortKey"
        :sort-order="sortOrder"
        :selected-ids="selection.selectedIds.value"
        :all-selected="selection.allSelected.value"
        :status-config="dt?.status_config"
        @sort="onSort"
        @select="selection.toggle"
        @select-all="onSelectAll"
        @row-click="navigateToDoc"
      />

      <ListPagination
        v-if="meta"
        :page="meta.page"
        :pages="meta.pages"
        :total="meta.total"
        :per-page="20"
        @update:page="page = $event"
      />
    </template>
  </div>
</template>
