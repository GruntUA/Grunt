<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { docsApi } from '@/core/api/docs'
import { useInfiniteDocTypeListData } from '@/core/composables/useInfiniteDocTypeListData'
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
import { useFastFilters } from '@/core/composables/useFastFilters'
import { buildQuickFiltersFromFields, mergeFastFilters, applyFieldSelection } from '@/core/quickFilters'
import { useQuickFilterPrefs } from '@/core/composables/useQuickFilterPrefs'
import { useDebounce } from '@/core/composables/useDebounce'
import { useBulkDeleteProgress } from '@/core/composables/useBulkDeleteProgress'
import { useListSelection } from '@/core/composables/useListSelection'
import { useDevMode } from '@/core/composables/useDevMode'
import type { DocType, FastFilter } from '@/types'
import { getRegisteredViews } from '@/core/viewRegistry'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'

// Shared UI components
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'

// Custom sub-components
import ListHeader from '@/components/views/list/ListHeader.vue'
import QuickFilterSettingsDialog from '@/components/views/list/QuickFilterSettingsDialog.vue'
import DocTypeToolbar from '@/components/views/DocTypeToolbar.vue'
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
// Bumped by the header's Refresh button — views with their own local fetch
// (tree/calendar/kanban) watch this to refetch; query-based views already
// refetch automatically from invalidateQueries below and ignore it.
const refreshKey = ref(0)
const { viewMode, sortKey, sortOrder, groupBy, activeFilters, fastFilterValues } = useListViewState(props.doctype)
const { inlineSearch, debouncedSearch } = useListSearch(page)

// ── Fast filters ─────────────────────────────────────────────────────────────
const quickFilterPrefs = useQuickFilterPrefs(props.doctype)
const showQuickFilterDialog = ref(false)

const fastFilterDefs = computed<FastFilter[]>(() => {
  const explicitDefs = dt.value?.list_view?.fast_filters ?? []
  const generatedDefs = buildQuickFiltersFromFields(dt.value?.fields ?? [])
  const adminDefaults = mergeFastFilters(explicitDefs, generatedDefs)
  const personalFields = quickFilterPrefs.selectedFields.value
  const merged = personalFields === null
    ? adminDefaults
    : applyFieldSelection(personalFields, adminDefaults, dt.value?.fields ?? [])

  const fallbackAsOfField = dt.value?.fields.find(
    f => f.fieldname === 'valid_from' && ['Date', 'Datetime'].includes(f.fieldtype),
  )?.fieldname
  const asOfField = dt.value?.tree_view?.as_of_date_field ?? fallbackAsOfField
  if (!asOfField) return merged

  const normalized: FastFilter[] = merged.map((ff) => {
    if (ff.field !== asOfField) return ff
    if (ff.operator === 'lte_or_null') return ff
    return {
      ...ff,
      id: ff.id === 'as_of_date' ? ff.id : 'as_of_date',
      label: ff.label ?? 'Станом на дату',
      operator: 'lte_or_null',
      input_type: 'date',
      enabled_in: (ff.enabled_in.includes('tree') ? ff.enabled_in : [...ff.enabled_in, 'tree']) as Array<'list' | 'tree'>,
    }
  })

  const hasAsOf = normalized.some(ff => ff.id === 'as_of_date' || ff.field === asOfField)
  if (hasAsOf) return normalized

  const asOfFastFilter: FastFilter = {
    id: 'as_of_date',
    field: asOfField,
    operator: 'lte_or_null',
    label: 'Станом на дату',
    input_type: 'date',
    on_change: { mode: 'local', debounce_ms: 150 },
    enabled_in: ['tree'],
  }

  return [...normalized, asOfFastFilter]
})
const { rawFastFilters, setFastFilterValue, setFastFilters } = useFastFilters(fastFilterDefs, 'list', fastFilterValues)
// Use the maximum debounce_ms across all local-mode filters active in list scope
const fastFilterDebounceMs = computed(() =>
  fastFilterDefs.value
    .filter(ff => ff.enabled_in.includes('list') && ff.on_change.mode !== 'external')
    .reduce((max, ff) => Math.max(max, ff.on_change.debounce_ms ?? 0), 0)
)
const debouncedFastFilters = useDebounce(rawFastFilters, fastFilterDebounceMs)

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
const {
  listButtons,
  listMenuItems,
  runListClientSetup,
  runFastFilterOnChange,
} = useListClientScripts({
  doctype: props.doctype,
  activeFilters,
  fastFilterValues,
  setFastFilterValue,
  setFastFilters,
  page,
  queryClient,
  dialog,
  toast,
})

watch(
  fastFilterValues,
  (next, prev) => {
    const prevValues = prev ?? {}
    const keys = new Set([...Object.keys(prevValues), ...Object.keys(next)])

    for (const id of keys) {
      const newValue = String(next[id] ?? '')
      const oldValue = String(prevValues[id] ?? '')
      if (newValue === oldValue) continue

      const def = fastFilterDefs.value.find(ff => ff.id === id)
      runFastFilterOnChange({
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

const { data, isLoading, isFetching, isFetchingNextPage, fetchNextPage, hasNextPage, meta, rows, exportCtx } = useInfiniteDocTypeListData({
  doctype: props.doctype,
  debouncedSearch,
  sortKey,
  sortOrder,
  groupBy,
  activeFilters,
  debouncedFastFilters,
  visibleKeys: colState.visibleKeys,
  visibleColumns: colState.visibleColumns,
  dt,
})

const { applyRouteState, setGroupByInRoute, applySort } = useListRouteSync({
  route,
  router,
  viewMode,
  groupBy,
  sortKey,
  sortOrder,
  activeFilters,
  fastFilterValues,
  validViews: getRegisteredViews().map((d) => d.type),
  getDefaultView: () => dt.value?.default_view ?? 'list',
  dt,
})

// Resolve display values (titles) for Link fields when filters are added from URL
watch(activeFilters, async (newFilters) => {
  if (!dt.value) return
  
  const filtersToResolve = newFilters.filter(f => !f.displayValue && f.value)
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

const { registerMapMenuItems, unregisterMapMenuItems } = useListMapMenuItems(listMenuItems)

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
  const ws = props.workspace ?? 'grunt'
  // Use generic routing for all DocTypes including DocType itself
  router.push(`/${ws}/${props.doctype}/${encodeURIComponent(String(docId))}`)
}

watch(() => props.doctype, async (newDoctype) => {
  dt.value = await dtStore.get(newDoctype)
  if (dt.value?.is_singleton) {
    router.replace(`/${props.workspace ?? 'grunt'}/${newDoctype}/${newDoctype}`)
    return
  }
  applyRouteState()
  await runListClientSetup()
}, { immediate: true })

</script>

<template>
  <div class="flex flex-1 flex-col gap-3 p-4 sm:p-5 lg:p-6 animate-in fade-in duration-500">
    <!-- Header -->
    <ListHeader :doctype="doctype" :dt="dt" :workspace="workspace" :meta="meta" :is-fetching="isFetching"
      :is-system-doc-type="doctype === 'DocType'" :show-dev-actions="!!(isDev && auth.user?.is_superadmin)"
      :list-buttons="listButtons" :list-menu-items="listMenuItems" :export-ctx="exportCtx"
      v-model:view-mode="viewMode"
      @refresh="queryClient.invalidateQueries({ queryKey: ['documents', doctype] }); refreshKey++"
      @create-quick="showQuickEntry = true"
      @customize-quick-filters="showQuickFilterDialog = true" />

    <!-- Toolbar -->
    <DocTypeToolbar
      v-if="colState"
      v-model:view-mode="viewMode"
      v-model:inline-search="inlineSearch"
      v-model:active-filters="activeFilters"
      :dt="dt"
      :doctype="doctype"
      :fast-filter-defs="fastFilterDefs"
      :fast-filter-values="fastFilterValues"
      :view-extras="{
        columns: colState,
        groupableFields,
        groupBy,
        groupByField,
        sortKey,
        sortOrder,
        sortableColumns: colState.allAvailableColumns.value,
      }"
      @update:fast-filter-values="fastFilterValues = $event"
      @update:group-by="setGroupBy"
      @sort="onSort"
      @reset="inlineSearch = ''; activeFilters = []; fastFilterValues = {}; page = 1"
    />

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
:search="debouncedSearch || undefined"
      :active-filters="activeFilters"
      :fast-filter-defs="fastFilterDefs"
      :fast-filter-values="fastFilterValues"
      @update:fast-filter-values="fastFilterValues = $event"
      :fetch-next-page="fetchNextPage"
      :has-next-page="hasNextPage"
      :is-fetching-next-page="isFetchingNextPage"
      :refresh-key="refreshKey"
      @sort="onSort"
      @row-click="navigateToDoc"
      @inline-update="inlineUpdate"
      :is-superadmin="!!auth.user?.is_superadmin"
      @delete="bulkDelete"
      @fast-delete="bulkFastDelete"
      @clear="clearSelection"
      @select-all="selectAllDocuments"
      @update="bulkUpdate"
      @toggle-group="(k) => collapsedGroups.has(k) ? collapsedGroups.delete(k) : collapsedGroups.add(k)"
      @register-menu-items="registerMapMenuItems"
      @unregister-menu-items="unregisterMapMenuItems"
    />
    <!-- Quick Entry Dialog -->
    <QuickEntryDialog v-if="showQuickEntry && dt" :dt="dt" :workspace="workspace" mode="list"
      @close="showQuickEntry = false" @saved="queryClient.invalidateQueries({ queryKey: ['documents', doctype] })" />

    <!-- Bulk delete progress dialog -->
    <Dialog v-if="deleteProgress" :open="deleteProgress.active">
      <DialogContent class="max-w-sm p-6" :show-close-button="false">
      <DialogTitle class="sr-only">Видалення записів</DialogTitle>
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
      </DialogContent>
    </Dialog>

    <QuickFilterSettingsDialog
      v-if="dt"
      v-model:open="showQuickFilterDialog"
      :dt="dt"
      :current-fields="fastFilterDefs.map((ff) => ff.field)"
      @save="quickFilterPrefs.setSelection($event)"
      @reset="quickFilterPrefs.reset()"
    />
  </div>
</template>
