<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, watch, provide } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { MULTI_VALUE_OPS, NO_VALUE_OPS, docsApi } from '@/core/api/docs'
import { useDocTypeListData } from '@/core/composables/useDocTypeListData'
import { useListRouteSync } from '@/core/composables/useListRouteSync'
import { useListActions } from '@/core/composables/useListActions'
import { useListMapMenuItems } from '@/core/composables/useListMapMenuItems'
import { useDocTypeStore } from '@/stores/doctype'
import { useAuthStore } from '@/stores/auth'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { useNotifications } from '@/core/composables/useNotifications'
import { useListColumns } from '@/core/composables/useListColumns'
import { useListViewState } from '@/core/composables/useListViewState'
import { useListSearch } from '@/core/composables/useListSearch'
import { useGrouping } from '@/core/composables/useGrouping'
import { useListClientScripts } from '@/core/composables/useListClientScripts'
import { useQuickFilters } from '@/core/composables/useQuickFilters'
import { buildQuickFiltersFromFields, applyFieldSelection } from '@/core/quickFilters'
import { useQuickFilterPrefs } from '@/core/composables/useQuickFilterPrefs'
import { useDebounce } from '@/core/composables/useDebounce'
import { useBulkDeleteProgress } from '@/core/composables/useBulkDeleteProgress'
import { useListSelection } from '@/core/composables/useListSelection'
import type { DocType, QuickFilter } from '@/types'
import { getRegisteredViews, getViewDef } from '@/core/viewRegistry'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'
import { setPageTitle } from '@/core/composables/usePageTitle'

// Shared UI components
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'

// Custom sub-components
import ListHeader from '@/components/views/list/ListHeader.vue'
import AppBreadcrumb from '@/components/app/AppBreadcrumb.vue'
import QuickFilterSettingsDialog from '@/components/views/list/QuickFilterSettingsDialog.vue'
import DocTypeToolbar from '@/components/views/DocTypeToolbar.vue'
import ListViewRouter from '@/components/views/list/ListViewRouter.vue'
import ListPagination from '@/components/views/ListPagination.vue'
import ListTreePanel from '@/components/views/list/ListTreePanel.vue'
import { provideRowDrag } from '@/core/composables/useRowDrag'
import { docUrl } from '@/core/workspaceUrl'
import { roleAllows } from '@/core/permissions'
import { getExporters } from '@/core/io/exporters/registry'
import { LIST_BULK_UI, type BulkRequest } from '@/core/composables/useListBulkUi'
import { LIST_FILTER_RESET } from '@/core/composables/useListFilterReset'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'

const { t } = useI18n()
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
const { onUserEvent, offUserEvent } = useNotifications()

// ── State ────────────────────────────────────────────────────────────────────
const dt = ref<DocType | null>(null)
const page = ref(1)
// Bumped by the header's Refresh button — views with their own local fetch
// (tree/calendar/kanban) watch this to refetch; query-based views already
// refetch automatically from invalidateQueries below and ignore it.
const refreshKey = ref(0)
const { viewMode, sortKey, sortOrder, groupBy, activeFilters, quickFilterValues, search, perPage } = useListViewState(props.doctype)
const { inlineSearch, debouncedSearch, resetSearch } = useListSearch(page, search)

// ── Quick filters ─────────────────────────────────────────────────────────────
const quickFilterPrefs = useQuickFilterPrefs(props.doctype)
const showQuickFilterDialog = ref(false)

const quickFilterDefs = computed<QuickFilter[]>(() => {
  // Admin-defined defaults are derived purely from fields flagged in_quick_filter.
  const adminDefaults = buildQuickFiltersFromFields(dt.value?.fields ?? [])
  const personalFields = quickFilterPrefs.selectedFields.value
  const merged = personalFields === null
    ? adminDefaults
    : applyFieldSelection(personalFields, adminDefaults, dt.value?.fields ?? [])

  const fallbackAsOfField = dt.value?.fields.find(
    f => f.fieldname === 'valid_from' && ['Date', 'Datetime'].includes(f.fieldtype),
  )?.fieldname
  const asOfField = dt.value?.tree_as_of_date_field ?? fallbackAsOfField
  if (!asOfField) return merged

  const normalized: QuickFilter[] = merged.map((ff) => {
    if (ff.field !== asOfField) return ff
    if (ff.operator === 'lte_or_null') return ff
    return {
      ...ff,
      id: ff.id === 'as_of_date' ? ff.id : 'as_of_date',
      label: ff.label ?? t('As of date'),
      operator: 'lte_or_null',
      input_type: 'date',
      enabled_in: (ff.enabled_in.includes('tree') ? ff.enabled_in : [...ff.enabled_in, 'tree']) as Array<'list' | 'tree'>,
    }
  })

  const hasAsOf = normalized.some(ff => ff.id === 'as_of_date' || ff.field === asOfField)
  if (hasAsOf) return normalized

  const asOfQuickFilter: QuickFilter = {
    id: 'as_of_date',
    field: asOfField,
    operator: 'lte_or_null',
    label: t('As of date'),
    input_type: 'date',
    on_change: { mode: 'local', debounce_ms: 150 },
    enabled_in: ['tree'],
  }

  return [...normalized, asOfQuickFilter]
})
const { rawQuickFilters, setQuickFilterValue, setQuickFilters } = useQuickFilters(quickFilterDefs, 'list', quickFilterValues)
// Use the maximum debounce_ms across all local-mode filters active in list scope
const quickFilterDebounceMs = computed(() =>
  quickFilterDefs.value
    .filter(ff => ff.enabled_in.includes('list') && ff.on_change.mode !== 'external')
    .reduce((max, ff) => Math.max(max, ff.on_change.debounce_ms ?? 0), 0)
)
const debouncedQuickFilters = useDebounce(rawQuickFilters, quickFilterDebounceMs)

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
const colState = useListColumns(props.doctype, () => dt.value?.fields ?? [], () => dt.value?.title_field)
const showQuickEntry = ref(false)
const dialog = useDialog()
// Bulk dialogs the selection bar opens on listview.bulk_edit() / bulk_delete() / fast_delete().
const bulkRequest = ref<BulkRequest>(null)

const {
  actions: listActions,
  runListClientSetup,
  runQuickFilterOnChange,
} = useListClientScripts({
  doctype: props.doctype,
  activeFilters,
  quickFilterValues,
  setQuickFilterValue,
  setQuickFilters,
  page,
  queryClient,
  dialog,
  toast,
  state: () => {
    const roles = auth.user?.roles ?? []
    return {
      perm: {
        create: roleAllows(dt.value, 'create', roles),
        write: roleAllows(dt.value, 'write', roles),
        delete: roleAllows(dt.value, 'delete', roles),
      },
      selected: selectedIds.value,
      allSelected: allSelected.value,
      isFetching: isFetching.value,
      exporters: getExporters().map((e) => ({ id: e.id, label: t(e.label) })),
      canExport: !!exportCtx.value,
      filters: activeFilters.value,
    }
  },
  ui: {
    newDoc: () => {
      if (dt.value?.quick_entry) showQuickEntry.value = true
      else router.push(docUrl(props.doctype, 'new', props.workspace))
    },
    bulkEdit: () => { bulkRequest.value = 'edit' },
    bulkDelete: () => { bulkRequest.value = 'delete' },
    fastDelete: () => { bulkRequest.value = 'fast-delete' },
    exportWith: (exporterId) => {
      const exporter = getExporters().find((e) => e.id === exporterId)
      if (exporter && exportCtx.value) void exporter.export(exportCtx.value)
    },
    customizeQuickFilters: () => { showQuickFilterDialog.value = true },
    createReport: () => {
      router.push({
        name: 'report-builder',
        params: { workspaceName: props.workspace ?? 'grunt' },
        query: { doctype: props.doctype },
      })
    },
    reloadMeta: async () => {
      dtStore.invalidate(props.doctype)
      dt.value = await dtStore.get(props.doctype)
    },
    refreshed: () => { refreshKey.value++ },
  },
})

provide(LIST_BULK_UI, { actions: listActions.resolved('bulk'), request: bulkRequest })
provide(LIST_FILTER_RESET, {
  active: computed(() =>
    !!debouncedSearch.value
    || activeFilters.value.length > 0
    || Object.values(quickFilterValues.value).some(Boolean),
  ),
  clear: () => {
    resetSearch()
    activeFilters.value = []
    quickFilterValues.value = {}
  },
})

watch(
  quickFilterValues,
  (next, prev) => {
    const prevValues = prev ?? {}
    const keys = new Set([...Object.keys(prevValues), ...Object.keys(next)])

    for (const id of keys) {
      const newValue = String(next[id] ?? '')
      const oldValue = String(prevValues[id] ?? '')
      if (newValue === oldValue) continue

      const def = quickFilterDefs.value.find(ff => ff.id === id)
      runQuickFilterOnChange({
        id,
        value: newValue,
        previousValue: oldValue,
        fieldname: def?.field,
        operator: def?.operator,
        source: def?.on_change?.source,
        viewScope: viewMode.value === 'tree' ? 'tree' : 'list',
      })
    }
  },
  { deep: true },
)

const { data, isLoading, isFetching, meta, rows, exportCtx } = useDocTypeListData({
  doctype: props.doctype,
  page,
  perPage,
  debouncedSearch,
  sortKey,
  sortOrder,
  groupBy,
  activeFilters,
  debouncedQuickFilters,
  visibleKeys: colState.visibleKeys,
  visibleColumns: colState.visibleColumns,
  dt,
})

// Any change to the result set (sort, filters, page size, grouping) resets to page 1.
watch(
  [sortKey, sortOrder, groupBy, perPage,
    () => JSON.stringify(activeFilters.value),
    () => JSON.stringify(debouncedQuickFilters.value)],
  () => { page.value = 1 },
)

// Views like kanban fill the viewport and scroll their own regions; bound the
// page to the viewport so their internal scrollbars stay in view, and drop the
// shared pager (they load their own data, not one page at a time).
const ownScrollView = computed(() => getViewDef(viewMode.value)?.managesOwnScroll ?? false)

// ── Tree navigation (DocType.list_tree_field) ─────────────────────────────────
// A Link to an `is_tree` DocType shown as a panel beside the list: its node is
// a filter; rows dragged onto a node are re-linked. Views that manage their own
// scroll (kanban, calendar…) keep the full width.
const treeNavField = computed(() => {
  const name = dt.value?.list_tree_field
  const f = name ? dt.value?.fields.find(ff => ff.fieldname === name && ff.fieldtype === 'Link') : null
  return f?.options ? f : null
})
const showTreeNav = computed(() => !!treeNavField.value && !ownScrollView.value)
provideRowDrag({ doctype: props.doctype, enabled: showTreeNav, selectedIds })

function onTreeRowsMoved() {
  clearSelection()
  queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
}

const { applyRouteState, setGroupByInRoute, applySort } = useListRouteSync({
  route,
  router,
  viewMode,
  groupBy,
  sortKey,
  sortOrder,
  activeFilters,
  quickFilterValues,
  validViews: getRegisteredViews().map((d) => d.type),
  getDefaultView: () => dt.value?.default_view ?? 'list',
  dt,
})

// Resolve display values (titles) for Link fields when filters are added from URL
watch(activeFilters, async (newFilters) => {
  if (!dt.value) return
  
  const filtersToResolve = newFilters.filter(f => !f.displayValue && f.value && !MULTI_VALUE_OPS.includes(f.op) && !(f.op in NO_VALUE_OPS))
  if (!filtersToResolve.length) return

  for (const f of filtersToResolve) {
    const field = dt.value.fields.find(ff => ff.fieldname === f.fieldname)
    if (field?.fieldtype === 'Link' && field.options) {
      try {
        const doc = await docsApi.get(field.options, String(f.value))
        if (doc) {
          f.displayValue = doc.name || doc.id
        }
      } catch (e) { console.error('Failed to resolve filter title', e) }
    }
  }
}, { deep: true })

const { bulkUpdate, inlineUpdate } = useListActions({
  doctype: props.doctype,
  selectedIds,
  allSelected,
  debouncedSearch,
  activeFilters,
  clearSelection,
  queryClient,
})

const { registerMapMenuItems, unregisterMapMenuItems } = useListMapMenuItems(listActions)

// ── Grouping Logic ───────────────────────────────────────────────────────────
const {
  collapsedGroups,
  groupableFields,
  groupedRows,
  groupByField,
  setGroupBy: baseSetGroupBy,
} = useGrouping({ dt, rows: computed(() => rows.value), groupBy, page })

function setGroupBy(field: string | null) {
  baseSetGroupBy(field)
  setGroupByInRoute(field)
}


// ── Handlers ─────────────────────────────────────────────────────────────────
function onSort(key: string) {
  applySort(key)
}

const { deleteProgress, bulkDelete, bulkFastDelete } = useBulkDeleteProgress({
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
  const docId = row.id ?? row.name
  if (docId === null || docId === undefined || String(docId).trim() === '') return
  // Optimistically mark the row seen for the current user so it dims on return —
  // the server records it for real via the form's after_read hook (track_seen).
  const seen = row._seen
  const email = auth.user?.email
  if (Array.isArray(seen) && email && !seen.includes(email)) {
    row._seen = [...seen, email]
  }
  // Use generic routing for all DocTypes including DocType itself
  router.push(docUrl(props.doctype, docId, props.workspace))
}

watch(() => props.doctype, async (newDoctype) => {
  dt.value = await dtStore.get(newDoctype)
  setPageTitle(dt.value?.label || newDoctype)
  if (dt.value?.is_singleton) {
    router.replace(docUrl(newDoctype, newDoctype, props.workspace))
    return
  }
  applyRouteState()
  await runListClientSetup()
}, { immediate: true })

</script>

<template>
  <div
    class="flex flex-1 flex-col gap-3 p-4 sm:p-5 lg:p-6 animate-in fade-in duration-500"
    :class="ownScrollView && 'h-full overflow-hidden pb-0'"
  >
    <AppBreadcrumb :workspace-name="workspace ?? 'grunt'" :doctype="doctype" :count="meta?.total ?? null">
      <template #actions>
        <ListHeader :doctype="doctype" :dt="dt" :actions="listActions" v-model:view-mode="viewMode" />
      </template>
    </AppBreadcrumb>

    <!-- Toolbar -->
    <DocTypeToolbar
      v-if="colState"
      v-model:view-mode="viewMode"
      v-model:inline-search="inlineSearch"
      v-model:active-filters="activeFilters"
      :dt="dt"
      :doctype="doctype"
      :quick-filter-defs="quickFilterDefs"
      :quick-filter-values="quickFilterValues"
      :view-extras="{
        columns: colState,
        groupableFields,
        groupBy,
        groupByField,
        sortKey,
        sortOrder,
        sortableColumns: colState.allAvailableColumns.value,
      }"
      @update:quick-filter-values="quickFilterValues = $event"
      @update:group-by="setGroupBy"
      @sort="onSort"
    />

    <div class="flex min-h-0 flex-1 gap-4" :class="ownScrollView && 'overflow-hidden'">
    <aside v-if="showTreeNav && dt && treeNavField"
      class="hidden w-56 shrink-0 md:block">
      <div class="sticky top-4 max-h-[calc(100vh-6rem)] overflow-y-auto pr-1">
        <ListTreePanel :dt="dt" :field="treeNavField" :workspace="workspace" :filters="activeFilters"
          @update:filters="activeFilters = $event" @moved="onTreeRowsMoved" />
      </div>
    </aside>
    <div class="flex min-w-0 flex-1 flex-col gap-3">
    <ListViewRouter
      v-if="dt && colState"
      :view-mode="viewMode"
      :dt="dt"
      :workspace="workspace"
      :doctype="doctype"
      :rows="rows"
      :fields="dt?.fields ?? []"
      :columns="colState.visibleColumns.value"
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
      :per-page="perPage"
      :search="debouncedSearch || undefined"
      :active-filters="activeFilters"
      :quick-filter-defs="quickFilterDefs"
      :quick-filter-values="quickFilterValues"
      @update:quick-filter-values="quickFilterValues = $event"
      @page="page = $event"
      @set-per-page="perPage = $event"
      :refresh-key="refreshKey"
      @sort="onSort"
      @row-click="navigateToDoc"
      @inline-update="inlineUpdate"
      :is-system-manager="!!auth.isSystemManager"
      @delete="bulkDelete"
      @fast-delete="bulkFastDelete"
      @clear="clearSelection"
      @select-all="selectAllDocuments"
      @update="bulkUpdate"
      @toggle-group="(k) => collapsedGroups.has(k) ? collapsedGroups.delete(k) : collapsedGroups.add(k)"
      @register-menu-items="registerMapMenuItems"
      @unregister-menu-items="unregisterMapMenuItems"
    />

    <!-- Pager stays pinned to the viewport bottom while the list scrolls behind it. -->
    <div
      v-if="!ownScrollView && meta && (rows.length > 0 || page > 1)"
      class="sticky bottom-0 z-10 -mx-4 border-t bg-background px-4 sm:-mx-5 sm:px-5 lg:-mx-6 lg:px-6"
    >
      <ListPagination
        :page="meta.page"
        :pages="meta.pages"
        :total="meta.total"
        :per-page="perPage"
        :selected-count="selectionCount"
        :show-per-page="!groupBy"
        @update:page="page = $event"
        @update:per-page="perPage = $event"
      />
    </div>

    </div>
    </div>

    <!-- Quick Entry Dialog -->
    <QuickEntryDialog v-if="showQuickEntry && dt" :dt="dt" :workspace="workspace" mode="list"
      @close="showQuickEntry = false" @saved="queryClient.invalidateQueries({ queryKey: ['documents', doctype] })" />

    <!-- Bulk delete progress dialog -->
    <Dialog v-if="deleteProgress" :open="deleteProgress.active">
      <DialogContent class="max-w-sm p-6" :show-close-button="false">
      <DialogTitle class="sr-only">{{ t('Deleting records') }}</DialogTitle>
      <div class="flex flex-col gap-4 py-2">
        <div class="flex items-center gap-3">
          <div class="size-5 shrink-0 rounded-full border-2 border-destructive/20 border-t-destructive animate-spin" />
          <p class="font-medium text-foreground">
            {{ t('Deleting records…') }}
          </p>
        </div>

        <!-- Progress bar -->
        <div class="flex flex-col gap-1.5">
          <div class="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div class="h-full rounded-full bg-destructive transition-all duration-300"
              :style="{ width: `${deleteProgress.total ? Math.round(deleteProgress.done / deleteProgress.total * 100) : 0}%` }" />
          </div>
          <div class="flex justify-between text-muted-foreground tabular-nums">
            <span>{{ deleteProgress.done }} / {{ deleteProgress.total }}</span>
            <span>{{ deleteProgress.total ? Math.round(deleteProgress.done / deleteProgress.total * 100) : 0
            }}%</span>
          </div>
        </div>

        <p v-if="deleteProgress.errors > 0" class="text-destructive">
          {{ t('Errors: {n}', { n: String(deleteProgress.errors) }) }}
        </p>
      </div>
      </DialogContent>
    </Dialog>

    <QuickFilterSettingsDialog
      v-if="dt"
      v-model:open="showQuickFilterDialog"
      :dt="dt"
      :current-fields="quickFilterDefs.map((ff) => ff.field)"
      @save="quickFilterPrefs.setSelection($event)"
      @reset="quickFilterPrefs.reset()"
    />
  </div>
</template>
