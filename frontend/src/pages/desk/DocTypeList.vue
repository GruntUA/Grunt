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
import { useListSearch, SEARCH_DEBOUNCE_MS } from '@/core/composables/useListSearch'
import { useGrouping } from '@/core/composables/useGrouping'
import { useListClientScripts } from '@/core/composables/useListClientScripts'
import { useQuickFilters } from '@/core/composables/useQuickFilters'
import { buildQuickFiltersFromFields, applyFieldSelection, withAsOfDateFilter } from '@/core/quickFilters'
import { useQuickFilterPrefs } from '@/core/composables/useQuickFilterPrefs'
import { useDebounce } from '@/core/composables/useDebounce'
import { useBulkDeleteProgress } from '@/core/composables/useBulkDeleteProgress'
import { useListSelection } from '@/core/composables/useListSelection'
import type { DocType, QuickFilter } from '@/types'
import { getRegisteredViews, getViewDef } from '@/core/viewRegistry'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'
import { setPageTitle } from '@/core/composables/usePageTitle'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import ListHeader from '@/components/views/list/ListHeader.vue'
import AppBreadcrumb from '@/components/app/AppBreadcrumb.vue'
import QuickFilterSettingsDialog from '@/components/views/list/QuickFilterSettingsDialog.vue'
import DocTypeToolbar from '@/components/views/DocTypeToolbar.vue'
import ListViewRouter from '@/components/views/list/ListViewRouter.vue'
import ListPagination from '@/components/views/ListPagination.vue'
import { docUrl } from '@/core/workspaceUrl'
import { roleAllows } from '@/core/permissions'
import { getExporters } from '@/core/io/exporters/registry'
import { LIST_BULK_UI, type BulkRequest } from '@/core/composables/useListBulkUi'
import { LIST_FILTER_RESET } from '@/core/composables/useListFilterReset'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { hasTrait } from '@/core/fieldRegistry'

// The parent keys this component by doctype, so `props.doctype` is fixed for
// its lifetime and composables take it as a plain string.
const props = defineProps<{ doctype: string; workspace?: string }>()
const workspace = computed(() => props.workspace ?? 'grunt')

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const dtStore = useDocTypeStore()
const auth = useAuthStore()
const queryClient = useQueryClient()
const toast = useToast()
const dialog = useDialog()
const { onUserEvent, offUserEvent } = useNotifications()

const invalidateList = () => queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
useWebSocket(`/api/v1/ws/${props.doctype}`).onEvent('doc_change', invalidateList)

const dt = ref<DocType | null>(null)
const page = ref(1)
// Bumped by the header's Refresh button - views with their own local fetch
// (tree/calendar/kanban) watch this to refetch; query-based views already
// refetch from invalidateQueries and ignore it.
const refreshKey = ref(0)
const showQuickEntry = ref(false)
const showQuickFilterDialog = ref(false)
// Bulk dialogs the selection bar opens on listview.bulk_edit() / bulk_delete() / fast_delete().
const bulkRequest = ref<BulkRequest>(null)

const { viewMode, sortKey, sortOrder, groupBy, activeFilters, quickFilterValues, search, perPage } = useListViewState(props.doctype)
const { inlineSearch, debouncedSearch, resetSearch } = useListSearch(page, search)

const viewDef = computed(() => getViewDef(viewMode.value))
// Views like kanban fill the viewport and scroll their own regions: bound the
// page to the viewport so their scrollbars stay in view, and drop the shared
// pager (they load their own data, not one page at a time).
const ownScrollView = computed(() => viewDef.value?.managesOwnScroll ?? false)
// Page is bounded to the viewport; the view scrolls inside it (pager may still show).
const boundedView = computed(() => ownScrollView.value || (viewDef.value?.fillsViewport ?? false))
const ownToolbar = computed(() => viewDef.value?.ownToolbar ?? false)

// Quick filters: admin defaults (fields flagged in_quick_filter), optionally
// replaced by the user's personal field selection.
const quickFilterPrefs = useQuickFilterPrefs(props.doctype)
const quickFilterDefs = computed<QuickFilter[]>(() => {
  if (!dt.value) return []
  const adminDefaults = buildQuickFiltersFromFields(dt.value.fields)
  const personalFields = quickFilterPrefs.selectedFields.value
  const merged = personalFields === null
    ? adminDefaults
    : applyFieldSelection(personalFields, adminDefaults, dt.value.fields)
  return withAsOfDateFilter(merged, dt.value, t('As of date'))
})
const { rawQuickFilters, setQuickFilterValue, setQuickFilters } = useQuickFilters(quickFilterDefs, 'list', quickFilterValues)
// The longest debounce among local-mode filters active in the list scope.
const quickFilterDebounceMs = computed(() =>
  quickFilterDefs.value
    .filter(ff => ff.enabled_in.includes('list') && ff.on_change.mode !== 'external')
    .reduce((max, ff) => Math.max(max, ff.on_change.debounce_ms ?? 0), 0),
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
  count: selectionCount,
} = useListSelection()

const colState = useListColumns(props.doctype, () => dt.value?.fields ?? [], () => dt.value?.title_field)

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
        params: { workspaceName: workspace.value },
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
    !!inlineSearch.value
    || activeFilters.value.length > 0
    || Object.values(quickFilterValues.value).some(Boolean),
  ),
  clear: () => {
    resetSearch()
    activeFilters.value = []
    quickFilterValues.value = {}
  },
})

// Fire the client-script on_change hook for every quick filter whose value changed.
watch(quickFilterValues, (next, prev = {}) => {
  const viewScope = viewMode.value === 'tree' ? 'tree' : 'list'
  for (const id of new Set([...Object.keys(prev), ...Object.keys(next)])) {
    const value = String(next[id] ?? '')
    const previousValue = String(prev[id] ?? '')
    if (value === previousValue) continue
    const def = quickFilterDefs.value.find(ff => ff.id === id)
    runQuickFilterOnChange({
      id,
      value,
      previousValue,
      fieldname: def?.field,
      operator: def?.operator,
      source: def?.on_change?.source,
      viewScope,
    })
  }
})

// Any change to the result set (sort, filters, search, page size, grouping) resets
// to page 1 - but not while the list hydrates: a page restored from `?page=` (e.g.
// coming back from a document) belongs to the state restored with it, and that
// state settles in steps (doctype meta, URL filters, debounced search/quick filters).
let hydrated = false
watch(
  [sortKey, sortOrder, groupBy, perPage, debouncedSearch,
    () => JSON.stringify(activeFilters.value),
    () => JSON.stringify(debouncedQuickFilters.value)],
  () => { if (hydrated) page.value = 1 },
)

const { applyRouteState, setGroupByInRoute, applySort } = useListRouteSync({
  route,
  router,
  viewMode,
  groupBy,
  sortKey,
  sortOrder,
  activeFilters,
  quickFilterValues,
  search: inlineSearch,
  debouncedSearch,
  page,
  validViews: getRegisteredViews().map((d) => d.type),
  getDefaultView: () => dt.value?.default_view ?? 'list',
  dt,
})

// Link filters that arrive from the URL carry only the id - fetch the linked
// record's title for the filter chip. Values in flight are skipped so the deep
// watcher, re-fired by our own displayValue writes, doesn't refetch them.
const resolvingTitles = new Set<string>()
async function resolveLinkFilterTitles() {
  if (!dt.value) return
  const fieldByName = new Map(dt.value.fields.map(f => [f.fieldname, f]))
  await Promise.all(activeFilters.value.map(async (f) => {
    if (f.displayValue || !f.value || MULTI_VALUE_OPS.includes(f.op) || f.op in NO_VALUE_OPS) return
    const field = fieldByName.get(f.fieldname)
    if (!field || !hasTrait(field.fieldtype, 'link') || !field.options) return
    const key = `${field.options}\0${f.value}`
    if (resolvingTitles.has(key)) return
    resolvingTitles.add(key)
    try {
      const [linkDt, doc] = await Promise.all([
        dtStore.get(field.options),
        docsApi.get(field.options, String(f.value)),
      ])
      const title = linkDt.title_field ? doc[linkDt.title_field] : null
      f.displayValue = String(title || doc.name || f.value)
    } catch (e) {
      console.error('Failed to resolve filter title', e)
    } finally {
      resolvingTitles.delete(key)
    }
  }))
}
watch(activeFilters, resolveLinkFilterTitles, { deep: true })
watch(dt, resolveLinkFilterTitles)

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

const {
  collapsedGroups,
  groupableFields,
  groupedRows,
  groupByField,
  setGroupBy: baseSetGroupBy,
} = useGrouping({ dt, rows, groupBy, page })

function setGroupBy(field: string | null) {
  baseSetGroupBy(field)
  setGroupByInRoute(field)
}

function toggleGroup(key: string) {
  const groups = collapsedGroups.value
  if (!groups.delete(key)) groups.add(key)
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
const deletePercent = computed(() => {
  const { done, total } = deleteProgress.value
  return total ? Math.round(done / total * 100) : 0
})

function navigateToDoc(row: Record<string, unknown>) {
  const docId = row.id ?? row.name
  if (docId == null || String(docId).trim() === '') return
  // Optimistically mark the row seen so it dims on return - the server records
  // it for real via the form's after_read hook (track_seen).
  const seen = row._seen
  const email = auth.user?.email
  if (Array.isArray(seen) && email && !seen.includes(email)) {
    row._seen = [...seen, email]
  }
  router.push(docUrl(props.doctype, docId, props.workspace))
}

void (async () => {
  dt.value = await dtStore.get(props.doctype)
  setPageTitle(dt.value?.label || props.doctype)
  applyRouteState()
  await runListClientSetup()
  // Let the debounced search / quick filters restored above land before user
  // changes start resetting the page.
  setTimeout(() => { hydrated = true }, Math.max(quickFilterDebounceMs.value, SEARCH_DEBOUNCE_MS) + 50)
})()
</script>

<template>
  <div
    class="flex flex-1 flex-col gap-3 p-4 sm:p-5 lg:p-6 animate-in fade-in duration-500"
    :class="boundedView && ['h-full overflow-hidden', ownScrollView ? 'pb-0' : 'pb-2 sm:pb-2 lg:pb-2']"
  >
    <AppBreadcrumb :workspace-name="workspace" :doctype="doctype" :count="meta?.total ?? null">
      <template #actions>
        <ListHeader v-model:view-mode="viewMode" :doctype="doctype" :dt="dt" :actions="listActions" />
      </template>
    </AppBreadcrumb>

    <DocTypeToolbar
      v-if="!ownToolbar"
      v-model:view-mode="viewMode"
      v-model:inline-search="inlineSearch"
      v-model:active-filters="activeFilters"
      v-model:quick-filter-values="quickFilterValues"
      :dt="dt"
      :doctype="doctype"
      :quick-filter-defs="quickFilterDefs"
      :view-extras="{
        columns: colState,
        groupableFields,
        groupBy,
        groupByField,
        sortKey,
        sortOrder,
        sortableColumns: colState.allAvailableColumns.value,
      }"
      @update:group-by="setGroupBy"
      @sort="applySort"
    />

    <div class="flex min-h-0 min-w-0 flex-1 flex-col gap-3" :class="boundedView && 'overflow-hidden'">
      <ListViewRouter
        v-if="dt"
        v-model:quick-filter-values="quickFilterValues"
        :view-mode="viewMode"
        :dt="dt"
        :workspace="workspace"
        :doctype="doctype"
        :rows="rows"
        :fields="dt.fields"
        :columns="colState.visibleColumns.value"
        :meta="meta"
        :is-loading="isLoading"
        :has-data="!!data"
        :selection-count="selectionCount"
        :selection="{ selectedIds, allSelected, isSelected, toggle: toggleSelection, toggleAll }"
        :image-field="dt.image_field ?? undefined"
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
        :refresh-key="refreshKey"
        :is-system-manager="!!auth.isSystemManager"
        @page="page = $event"
        @set-per-page="perPage = $event"
        @sort="applySort"
        @row-click="navigateToDoc"
        @inline-update="inlineUpdate"
        @update="bulkUpdate"
        @delete="bulkDelete"
        @fast-delete="bulkFastDelete"
        @clear="clearSelection"
        @select-all="selectAllDocuments"
        @toggle-group="toggleGroup"
        @register-menu-items="registerMapMenuItems"
        @unregister-menu-items="unregisterMapMenuItems"
      />

      <ListPagination
        v-if="!ownScrollView && meta && (rows.length > 0 || page > 1)"
        class="shrink-0"
        v-model:per-page="perPage"
        :page="meta.page"
        :pages="meta.pages"
        :total="meta.total"
        :selected-count="selectionCount"
        :show-per-page="!groupBy"
        @update:page="page = $event"
      />
    </div>

    <QuickEntryDialog
      v-if="showQuickEntry && dt"
      :dt="dt"
      :workspace="workspace"
      mode="list"
      @close="showQuickEntry = false"
      @saved="invalidateList"
    />

    <Dialog v-if="deleteProgress" :open="deleteProgress.active">
      <DialogContent class="max-w-sm p-6" :show-close-button="false">
        <DialogTitle class="sr-only">{{ t('Deleting records') }}</DialogTitle>
        <div class="flex flex-col gap-4 py-2">
          <div class="flex items-center gap-3">
            <div class="size-5 shrink-0 rounded-full border-2 border-destructive/20 border-t-destructive animate-spin" />
            <p class="font-medium text-foreground">{{ t('Deleting records…') }}</p>
          </div>
          <div class="flex flex-col gap-1.5">
            <Progress :model-value="deletePercent" class="h-2 *:data-[slot=progress-indicator]:bg-destructive" />
            <div class="flex justify-between text-muted-foreground tabular-nums">
              <span>{{ deleteProgress.done }} / {{ deleteProgress.total }}</span>
              <span>{{ deletePercent }}%</span>
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
