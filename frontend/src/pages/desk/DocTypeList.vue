<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { useListViewKeyboard } from '@/core/composables/useListViewKeyboard'
import { useListFieldDetection } from '@/core/composables/useListFieldDetection'
import { useDocTypeListData } from '@/core/composables/useDocTypeListData'
import { useListRouteSync } from '@/core/composables/useListRouteSync'
import { useListActions } from '@/core/composables/useListActions'
import { useDocTypeStore } from '@/stores/doctype'
import { useAuthStore } from '@/stores/auth'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { useNotifications } from '@/core/composables/useNotifications'
import { useListColumns } from '@/core/composables/useListColumns'
import { useListViewState } from '@/core/composables/useListViewState'
import { useListSearch } from '@/core/composables/useListSearch'
import { useGrouping } from '@/core/composables/useGrouping'
import { useListClientScripts } from '@/core/composables/useListClientScripts'
import { useBulkDeleteProgress } from '@/core/composables/useBulkDeleteProgress'
import { useListSelection } from '@/core/composables/useListSelection'
import { useDevMode } from '@/core/composables/useDevMode'
import type { DocType, ScriptMenuItem } from '@/types'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'

// Shared UI components
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'

// Custom sub-components
import ListHeader from '@/components/views/list/ListHeader.vue'
import ListToolbar from '@/components/views/list/ListToolbar.vue'
import ListViewRouter from '@/components/views/list/ListViewRouter.vue'

const props = defineProps<{ doctype: string; workspace?: string }>()
const doctype = computed(() => props.doctype)
const workspace = computed(() => props.workspace ?? 'grunt')

const router = useRouter()
const route = useRoute()
const dtStore = useDocTypeStore()
const auth = useAuthStore()
const queryClient = useQueryClient()
const toast = useToast()

// ── WebSocket ────────────────────────────────────────────────────────────────
const listWs = useWebSocket(`/api/v1/ws/${props.doctype}`)
listWs.onEvent('doc_change', () => {
  queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
})
const { isDev } = useDevMode()
const { onUserEvent, offUserEvent } = useNotifications()

// ── State ────────────────────────────────────────────────────────────────────
const dt = ref<DocType | null>(null)
const page = ref(1)
type ViewMode = 'list' | 'kanban' | 'calendar' | 'tree' | 'gallery' | 'map'
const VALID_VIEWS: ViewMode[] = ['list', 'kanban', 'calendar', 'tree', 'gallery', 'map']

const { viewMode, sortKey, sortOrder, groupBy, activeFilters } = useListViewState(props.doctype)
const { inlineSearch, debouncedSearch } = useListSearch(page)

const {
  selectedIds,
  allSelected,
  isSelected,
  toggle: toggleSelection,
  toggleAll,
  selectAllDocuments,
  clear: clearSelection,
  count: selectionCount
} = useListSelection()
const columns = useListColumns(props.doctype, () => dt.value?.fields ?? [], () => dt.value?.title_field)
const showQuickEntry = ref(false)
const dialog = useDialog()
const {
  listButtons,
  listMenuItems,
  runListClientSetup,
} = useListClientScripts({
  doctype: props.doctype,
  activeFilters,
  page,
  queryClient,
  dialog,
  toast,
})

const { data, isLoading, isFetching, meta, rows, exportCtx } = useDocTypeListData({
  doctype: props.doctype,
  page,
  debouncedSearch,
  sortKey,
  sortOrder,
  groupBy,
  activeFilters,
  visibleKeys: columns.visibleKeys,
  visibleColumns: columns.visibleColumns,
  dt,
})

const { applyRouteState, setGroupByInRoute, applySort } = useListRouteSync({
  route,
  router,
  viewMode,
  groupBy,
  sortKey,
  sortOrder,
  validViews: VALID_VIEWS,
  getDefaultView: () => dt.value?.default_view ?? 'list',
})

const { bulkUpdate, inlineUpdate } = useListActions({
  doctype: props.doctype,
  selectedIds,
  allSelected,
  debouncedSearch,
  activeFilters,
  clearSelection,
  queryClient,
})

// ── Grouping Logic ───────────────────────────────────────────────────────────
const {
  collapsedGroups,
  groupableFields,
  groupedRows,
  groupByField,
  setGroupBy: baseSetGroupBy,
} = useGrouping({ dt, rows: computed(() => (data.value?.data ?? []) as Record<string, unknown>[]), groupBy, page })

function setGroupBy(field: string | null) {
  baseSetGroupBy(field)
  setGroupByInRoute(field)
}

onMounted(async () => {
  dt.value = await dtStore.get(props.doctype)
  if (dt.value?.is_singleton) {
    router.replace(`/${props.workspace ?? 'grunt'}/${props.doctype}/${props.doctype}`)
    return
  }

  applyRouteState()

  await runListClientSetup()
})

// ── View Detection ───────────────────────────────────────────────────────────
const { kanbanColumnField, treeParentField, geoField, calendarDateField } = useListFieldDetection(
  computed(() => dt.value)
)

// ── Handlers ─────────────────────────────────────────────────────────────────
function onSort(key: string) {
  applySort(key)
}

const { deleteProgress, bulkDelete } = useBulkDeleteProgress({
  doctype: props.doctype,
  metaTotal: computed(() => meta.value?.total ?? 0),
  selectedIds,
  allSelected,
  activeFilters,
  debouncedSearch,
  clearSelection,
  queryClient,
  onUserEvent,
  offUserEvent,
})

function navigateToDoc(row: Record<string, unknown>) {
  const ws = props.workspace ?? 'grunt'
  props.doctype === 'DocType' ? router.push(`/${ws}/DocType/${row.name}`) : router.push(`/${ws}/${props.doctype}/${row.id}`)
}

function registerMapMenuItems(items: ScriptMenuItem[]) {
  listMenuItems.value.push(...items)
}

function unregisterMapMenuItems(items: ScriptMenuItem[]) {
  for (const item of items) {
    const idx = listMenuItems.value.indexOf(item)
    if (idx !== -1) listMenuItems.value.splice(idx, 1)
  }
}

// ── Keyboard Shortcuts ───────────────────────────────────────────────────────
const { activeIndex } = useListViewKeyboard({
  rows: computed(() => rows.value),
  selectedIds,
  allSelected,
  toggleSelection,
  onOpenDoc: navigateToDoc,
  onBulkDelete: bulkDelete,
  onConfirmDelete: (title, subtitle) => dialog.confirm(title, subtitle),
})
</script>

<template>
  <div class="flex flex-1 flex-col gap-5 p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500">
    <!-- Header -->
    <ListHeader :doctype="doctype" :dt="dt" :workspace="workspace" :meta="meta" :is-fetching="isFetching"
      :is-system-doc-type="doctype === 'DocType'" :show-dev-actions="!!(isDev && auth.user?.is_superadmin)"
      :list-buttons="listButtons" :list-menu-items="listMenuItems" :export-ctx="exportCtx"
      @refresh="queryClient.invalidateQueries({ queryKey: ['documents', doctype] })"
      @create-quick="showQuickEntry = true" />

    <!-- Toolbar -->
    <ListToolbar v-model:view-mode="viewMode" v-model:inline-search="inlineSearch"
      v-model:active-filters="activeFilters" :group-by="groupBy" @update:group-by="setGroupBy" :dt="dt"
      :doctype="doctype" :columns="columns" :groupable-fields="groupableFields" :group-by-field="groupByField"
      :kanban-column-field="kanbanColumnField" :tree-parent-field="treeParentField"
      :calendar-date-field="calendarDateField" :geo-field="geoField"
      @reset="inlineSearch = ''; activeFilters = []; page = 1" />

    <ListViewRouter
      :view-mode="viewMode"
      :dt="dt"
      :workspace="workspace"
      :doctype="doctype"
      :rows="rows"
      :fields="dt?.fields ?? []"
      :columns="columns.visibleColumns.value"
      :meta="meta"
      :is-loading="isLoading"
      :has-data="!!data"
      :selection-count="selectionCount"
      :selection="{ selectedIds, allSelected, isSelected, toggle: toggleSelection, toggleAll }"
      :image-field="dt?.image_field ?? undefined"
      :group-by="groupBy"
      :grouped-rows="groupedRows"
      :collapsed-groups="collapsedGroups"
      :group-by-field="groupByField"
      :sort-key="sortKey"
      :sort-order="sortOrder"
      :active-index="activeIndex"
      :kanban-column-field="kanbanColumnField"
      :calendar-date-field="calendarDateField"
      :tree-parent-field="treeParentField"
      :geo-field="geoField"
      :search="debouncedSearch || undefined"
      :active-filters="activeFilters"
      @sort="onSort"
      @row-click="navigateToDoc"
      @inline-update="inlineUpdate"
      @delete="bulkDelete"
      @clear="clearSelection"
      @select-all="selectAllDocuments"
      @update="bulkUpdate"
      @toggle-group="(k) => collapsedGroups.has(k) ? collapsedGroups.delete(k) : collapsedGroups.add(k)"
      @page="page = $event"
      @register-menu-items="registerMapMenuItems"
      @unregister-menu-items="unregisterMapMenuItems"
    />
    <!-- Quick Entry Dialog -->
    <QuickEntryDialog v-if="showQuickEntry && dt" :dt="dt" :workspace="workspace" mode="list"
      @close="showQuickEntry = false" @saved="queryClient.invalidateQueries({ queryKey: ['documents', doctype] })" />

    <!-- Bulk delete progress dialog -->
    <Dialog :visible="deleteProgress.active" modal :closable="false" :show-header="false"
      :pt="{ root: { class: 'max-w-sm' }, content: { class: 'p-6' } }">
      <div class="flex flex-col gap-4 py-2">
        <div class="flex items-center gap-3">
          <div class="size-5 shrink-0 rounded-full border-2 border-destructive/20 border-t-destructive animate-spin" />
          <p class="text-sm font-medium text-foreground">
            Видалення записів…
          </p>
        </div>

        <!-- Progress bar -->
        <div class="flex flex-col gap-1.5">
          <div class="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div class="h-full rounded-full bg-destructive transition-all duration-300"
              :style="{ width: `${deleteProgress.total ? Math.round(deleteProgress.done / deleteProgress.total * 100) : 0}%` }" />
          </div>
          <div class="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>{{ deleteProgress.done }} / {{ deleteProgress.total }}</span>
            <span>{{ deleteProgress.total ? Math.round(deleteProgress.done / deleteProgress.total * 100) : 0
            }}%</span>
          </div>
        </div>

        <p v-if="deleteProgress.errors > 0" class="text-xs text-destructive">
          Помилок: {{ deleteProgress.errors }}
        </p>
      </div>
    </Dialog>
  </div>
</template>
