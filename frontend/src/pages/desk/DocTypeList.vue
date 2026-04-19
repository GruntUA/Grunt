<script setup lang="ts">
import { ref, computed, onMounted, watch, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useShortcut } from '@/core/composables/useShortcuts'
import { useDocTypeStore } from '@/stores/doctype'
import { useAuthStore } from '@/stores/auth'
import { useWebSocket } from '@/core/composables/useWebSocket'
import { useNotifications } from '@/core/composables/useNotifications'
import { useListSelection } from '@/core/composables/useListSelection'
import { useListColumns } from '@/core/composables/useListColumns'
import { useListViewState } from '@/core/composables/useListViewState'
import { useDevMode } from '@/core/composables/useDevMode'
import { docsApi, OP_MAP } from '@/core/api/docs'
import type { ActiveFilter, DocType, DocField, ScriptButton, ScriptMenuItem } from '@/types'
import {
  createListViewProxy,
  createGruntProxy,
  executeListSetup,
} from '@/core/scripting/executor'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'
import type { ExportContext } from '@/core/io'
import { getFieldDef } from '@/core/fieldRegistry'

// Shared UI components
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import BulkActionBar from '@/components/views/BulkActionBar.vue'
import GruntDataTable from '@/components/views/GruntDataTable.vue'
import ListPagination from '@/components/views/ListPagination.vue'
import KanbanView from '@/components/views/KanbanView.vue'
import CalendarView from '@/components/views/CalendarView.vue'
import TreeView from '@/components/views/TreeView.vue'
import GalleryView from '@/components/views/GalleryView.vue'
import MapView from '@/components/views/MapView.vue'

// Custom sub-components
import ListHeader from '@/components/views/list/ListHeader.vue'
import ListToolbar from '@/components/views/list/ListToolbar.vue'
import ListGroupedView from '@/components/views/list/ListGroupedView.vue'

const props = defineProps<{ doctype: string; workspace?: string }>()
const toast = useToast()
const router = useRouter()
const route = useRoute()
const dtStore = useDocTypeStore()
const auth = useAuthStore()
const queryClient = useQueryClient()

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
const debouncedSearch = ref('')
type ViewMode = 'list' | 'kanban' | 'calendar' | 'tree' | 'gallery' | 'map'
const VALID_VIEWS: ViewMode[] = ['list', 'kanban', 'calendar', 'tree', 'gallery', 'map']

const { viewMode, sortKey, sortOrder, groupBy, activeFilters } = useListViewState(props.doctype)
const inlineSearch = ref('')
const collapsedGroups = ref<Set<string>>(new Set())

let searchDebounce: ReturnType<typeof setTimeout>
watch(inlineSearch, (v) => {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => { debouncedSearch.value = v; page.value = 1 }, 400)
})

const selection = useListSelection()
const columns = useListColumns(props.doctype, () => dt.value?.fields ?? [], () => dt.value?.title_field)
const listButtons = ref<ScriptButton[]>([])
const listMenuItems = ref<ScriptMenuItem[]>([])
const showQuickEntry = ref(false)
const dialog = useDialog()

// ── Grouping Logic ───────────────────────────────────────────────────────────
const groupableFields = computed(() => {
  if (!dt.value) return []
  return dt.value.fields.filter((f: DocField) => {
    if (f.hidden) return false
    const def = getFieldDef(f.fieldtype)
    if (!def) return false
    if (def.is_layout || def.non_groupable) return false
    return f.in_list_view || f.in_filter
  })
})

const groupedRows = computed(() => {
  if (!groupBy.value) return null
  const field = groupBy.value
  const groups = new Map<string, Record<string, unknown>[]>()
  for (const row of rows.value) {
    const key = String(row[field] ?? '')
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(row)
  }
  return [...groups.entries()].map(([key, items]) => ({ key, items }))
})

const groupByField = computed(() => groupableFields.value.find(f => f.fieldname === groupBy.value) ?? null)

function setGroupBy(field: string | null) {
  groupBy.value = field
  collapsedGroups.value = new Set()
  page.value = 1
  const query = { ...route.query }
  if (field) query.groupBy = field; else delete query.groupBy
  router.replace({ query })
}

onMounted(async () => {
  dt.value = await dtStore.get(props.doctype)
  if (dt.value?.is_singleton) {
    router.replace(`/${props.workspace ?? 'grunt'}/list/${props.doctype}/${props.doctype}`)
    return
  }

  // URL params override localStorage; fall back to localStorage, then doctype default
  const urlView = route.query.view as string | undefined
  if (VALID_VIEWS.includes(urlView as ViewMode)) {
    viewMode.value = urlView as ViewMode
  } else if (!VALID_VIEWS.includes(viewMode.value)) {
    viewMode.value = (dt.value?.default_view ?? 'list') as ViewMode
  }

  if (route.query.groupBy) groupBy.value = route.query.groupBy as string
  if (route.query.sort) sortKey.value = route.query.sort as string
  if (['asc', 'desc'].includes(route.query.order as string)) sortOrder.value = route.query.order as any

  // Client scripts
  const gruntProxy = createGruntProxy({
    msgprint: (msgOrOpts) => dialog.msgprint(
      typeof msgOrOpts === 'string' ? msgOrOpts : { message: msgOrOpts.message, title: msgOrOpts.title, indicator: msgOrOpts.indicator }
    ),
    confirm: (msg, title) => dialog.confirm(msg, title),
    showAlert: (msg, type) => {
      if (type === 'error') toast.error(msg)
      else if (type === 'success') toast.success(msg)
      else if (type === 'warning') toast.warning(msg)
      else toast.info(msg)
    },
    prompt: (labelOrOpts, title) => dialog.prompt(labelOrOpts as any, title),
    warn: (title, message, primaryLabel) => dialog.confirm(`${title}\n${message}`, primaryLabel),
    form: (opts) => dialog.form(opts as any),
    showProgress: (title, count, total, description) => dialog.progress(title, count, total, description),
  })
  const listview = createListViewProxy(props.doctype, {
    addButton(label, action, options) {
      const btn: ScriptButton = { label, action, severity: options?.variant }
      const idx = listButtons.value.push(btn) - 1
      return { update(updates) { listButtons.value[idx] = { ...listButtons.value[idx], ...updates } } }
    },
    addMenuItem(label, action, options) {
      const item: ScriptMenuItem = { label, action, separator_before: options?.separator_before }
      const idx = listMenuItems.value.push(item) - 1
      return {
        update(updates) { listMenuItems.value[idx] = { ...listMenuItems.value[idx], ...updates } },
        remove() { listMenuItems.value.splice(idx, 1) },
      }
    },
    refresh() { queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] }) },
    setFilters(filters) {
      activeFilters.value = filters.map(f => ({
        fieldname: f.fieldname,
        label: f.label ?? f.fieldname,
        fieldtype: f.fieldtype,
        op: f.op,
        value: f.value,
      }))
      page.value = 1
    },
  })
  await executeListSetup(props.doctype, listview, gruntProxy)
})

watch(viewMode, (v) => {
  const query = { ...route.query }
  if (v === (dt.value?.default_view ?? 'list')) delete query.view; else query.view = v
  router.replace({ query })
})

// ── View Detection ───────────────────────────────────────────────────────────
const kanbanColumnField = computed(() => dt.value?.fields.find(f => f.fieldtype === 'Select' && f.in_list_view && !f.hidden) ?? null)
const treeParentField = computed(() => {
  if (!dt.value) return null
  if (dt.value.tree_view?.parent_field) return dt.value.fields.find(f => f.fieldname === dt.value!.tree_view!.parent_field) ?? null
  return dt.value.fields.find(f => f.fieldtype === 'Link' && f.options === dt.value!.name) ?? null
})
const geoField = computed(() => {
  if (!dt.value) return null
  const override = dt.value.map_view?.geo_field
  if (override) return dt.value.fields.find(f => f.fieldname === override) ?? null
  return dt.value.fields.find(f => f.fieldtype === 'Geolocation' && f.in_list_view && !f.hidden) ?? null
})

const calendarDateField = computed(() => {
  if (!dt.value) return null
  const f = dt.value.calendar_view?.field
  if (f && new Set(['created_at', 'modified_at']).has(f)) return { fieldname: f, fieldtype: 'Datetime', label: f } as DocField
  return (f && dt.value.fields.find(field => field.fieldname === f)) || dt.value.fields.find(field => field.fieldtype === 'Date' || field.fieldtype === 'Datetime') || null
})

// ── Data Fetching ────────────────────────────────────────────────────────────
const listFields = computed(() => {
  const fields = new Set([...columns.visibleKeys.value, 'modified_at', 'docstatus'])
  if (groupBy.value) fields.add(groupBy.value)
  if (sortKey.value) fields.add(sortKey.value)
  if (dt.value?.status_config?.field) fields.add(dt.value.status_config.field)
  if (dt.value?.image_field) fields.add(dt.value.image_field)
  return [...fields].join(',')
})

const { data, isLoading, isFetching } = useQuery({
  queryKey: computed(() => ['documents', props.doctype, page.value, debouncedSearch.value, sortKey.value, sortOrder.value, JSON.stringify(activeFilters.value), groupBy.value, listFields.value]),
  queryFn: () => docsApi.list(props.doctype, {
    page: page.value,
    per_page: groupBy.value ? 100 : 20,
    search: debouncedSearch.value || undefined,
    sort: groupBy.value ?? sortKey.value ?? undefined,
    order: groupBy.value ? 'asc' : (sortKey.value ? sortOrder.value : undefined),
    filters: activeFilters.value,
    fields: listFields.value,
  }),
  refetchOnMount: 'always',
})

const meta = computed(() => data.value?.meta)
const rows = computed(() => (data.value?.data ?? []) as Record<string, unknown>[])

const exportCtx = computed<ExportContext>(() => ({
  doctypeName: props.doctype,
  doctypeLabel: dt.value?.label ?? props.doctype,
  rows: rows.value,
  columns: columns.visibleColumns.value,
  fields: dt.value?.fields ?? [],
  filters: activeFilters.value,
  statusConfig: dt.value?.status_config ?? null,
  total: meta.value?.total ?? rows.value.length,
  groupBy: groupBy.value,
  getAll: async () => {
    const total = meta.value?.total ?? 0
    const result = await docsApi.list(props.doctype, {
      page: 1,
      per_page: Math.min(total, 10_000),
      search: debouncedSearch.value || undefined,
      sort: groupBy.value ?? sortKey.value ?? undefined,
      order: groupBy.value ? 'asc' : (sortKey.value ? sortOrder.value : undefined),
      filters: activeFilters.value,
      fields: listFields.value,
    })
    return result.data as Record<string, unknown>[]
  },
}))

// ── Handlers ─────────────────────────────────────────────────────────────────
function onSort(key: string) {
  sortOrder.value = sortKey.value === key && sortOrder.value === 'asc' ? 'desc' : 'asc'
  sortKey.value = key
  router.replace({ query: { ...route.query, sort: key, order: sortOrder.value } })
}

// ── Bulk delete progress ─────────────────────────────────────────────────────
const deleteProgress = ref({ active: false, total: 0, done: 0, errors: 0 })

// Stored so onUnmounted can clean up if navigation happens mid-delete
let _deleteProgressHandler: ((d: Record<string, unknown>) => void) | null = null
let _deleteDoneHandler: ((d: Record<string, unknown>) => void) | null = null

onUnmounted(() => {
  if (_deleteProgressHandler) offUserEvent('bulk_delete_progress', _deleteProgressHandler)
  if (_deleteDoneHandler) offUserEvent('bulk_delete_done', _deleteDoneHandler)
})

function buildRawFilters(filters: ActiveFilter[]): Record<string, string> {
  const raw: Record<string, string> = {}
  for (const f of filters) {
    raw[`${f.fieldname}__${OP_MAP[f.op] ?? 'eq'}`] = f.value
  }
  return raw
}

async function bulkDelete() {
  const ids = selection.allSelected.value ? [] : selection.selectedIds.value
  if (!selection.allSelected.value && !ids.length) return

  const total = selection.allSelected.value ? (meta.value?.total ?? 0) : ids.length
  deleteProgress.value = { active: true, total, done: 0, errors: 0 }

  function onProgress(data: Record<string, unknown>) {
    deleteProgress.value.done = (data.done as number) ?? deleteProgress.value.done
    deleteProgress.value.errors = (data.errors as number) ?? deleteProgress.value.errors
  }

  function onDone(_data: Record<string, unknown>) {
    offUserEvent('bulk_delete_progress', onProgress)
    offUserEvent('bulk_delete_done', onDone)
    _deleteProgressHandler = null
    _deleteDoneHandler = null
    deleteProgress.value.active = false
    selection.clear()
    queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
  }

  _deleteProgressHandler = onProgress
  _deleteDoneHandler = onDone
  onUserEvent('bulk_delete_progress', onProgress)
  onUserEvent('bulk_delete_done', onDone)

  try {
    if (selection.allSelected.value) {
      await docsApi.bulkDelete(props.doctype, [], {
        deleteAll: true,
        rawFilters: buildRawFilters(activeFilters.value),
        search: debouncedSearch.value || undefined,
      })
    } else {
      await docsApi.bulkDelete(props.doctype, ids)
    }
  } catch {
    offUserEvent('bulk_delete_progress', onProgress)
    offUserEvent('bulk_delete_done', onDone)
    _deleteProgressHandler = null
    _deleteDoneHandler = null
    deleteProgress.value.active = false
  }
}

async function bulkUpdate(field: string, value: string) {
  const ids = selection.allSelected.value ? (await docsApi.list(props.doctype, { page: 1, per_page: 10000, fields: 'id', search: debouncedSearch.value || undefined, filters: activeFilters.value })).data.map((r: any) => String(r.id)) : selection.selectedIds.value
  if (ids.length) await docsApi.bulkUpdate(props.doctype, ids, field, value)
  selection.clear(); queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
}

async function onInlineUpdate(rowId: string, field: string, value: string) {
  await docsApi.update(props.doctype, rowId, { [field]: value })
  queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
}

const activeIndex = ref(0)
watch(rows, () => { activeIndex.value = 0 })

useShortcut(['ArrowDown', 'j'], () => {
  if (!rows.value.length) return
  activeIndex.value = Math.min(activeIndex.value + 1, rows.value.length - 1)
}, { preventDefault: true })

useShortcut(['ArrowUp', 'k'], () => {
  if (!rows.value.length) return
  activeIndex.value = Math.max(activeIndex.value - 1, 0)
}, { preventDefault: true })

useShortcut(['Enter', 'o'], () => {
  if (rows.value[activeIndex.value]) {
    navigateToDoc(rows.value[activeIndex.value])
  }
}, { preventDefault: true })

useShortcut(['x'], () => {
  if (rows.value[activeIndex.value]) {
    selection.toggle(String(rows.value[activeIndex.value].id))
  }
}, { preventDefault: true })

useShortcut(['Delete', 'Backspace'], () => {
  if (selection.selectedIds.value.length > 0 || selection.allSelected.value) {
    dialog.confirm('Видалити виділені документи?', 'Обережно').then(ok => {
      if (ok) bulkDelete()
    })
  }
}, { preventDefault: true })

function navigateToDoc(row: Record<string, unknown>) {
  const ws = props.workspace ?? 'grunt'
  props.doctype === 'DocType' ? router.push(`/${ws}/list/DocType/${row.name}`) : router.push(`/${ws}/list/${props.doctype}/${row.id}`)
}
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
      @reset="inlineSearch = ''; debouncedSearch = ''; activeFilters = []; page = 1" />

    <!-- Main Content Area -->
    <div class="flex-1 min-h-0">
      <div v-if="viewMode === 'kanban' && kanbanColumnField && dt" class="h-[calc(100vh-14rem)]">
        <KanbanView :doctype="dt" :column-field="kanbanColumnField.fieldname" />
      </div>
      <div v-else-if="viewMode === 'calendar' && calendarDateField && dt" class="h-[calc(100vh-14rem)]">
        <CalendarView :doctype="dt" :date-field="calendarDateField.fieldname" :workspace="workspace" />
      </div>
      <div v-else-if="viewMode === 'tree' && treeParentField && dt">
        <TreeView :doctype="dt" :parent-field="treeParentField.fieldname" :workspace="workspace" />
      </div>
      <div v-else-if="viewMode === 'map' && geoField && dt">
        <MapView :doctype="dt" :geo-field="geoField.fieldname" :workspace="workspace"
          :search="debouncedSearch || undefined" :filters="activeFilters"
          @register-menu-items="(items) => listMenuItems.push(...items)"
          @unregister-menu-items="(items) => { for (const item of items) { const i = listMenuItems.indexOf(item); if (i !== -1) listMenuItems.splice(i, 1) } }" />
      </div>
      <div v-else-if="viewMode === 'gallery'">
        <BulkActionBar :count="selection.allSelected.value ? (meta?.total ?? 0) : selection.selectedIds.value.length"
          :total="meta?.total" :all-selected="selection.allSelected.value" :page-count="rows.length"
          :editable-fields="dt?.fields" @delete="bulkDelete" @clear="selection.clear"
          @select-all="selection.selectAllDocuments" @update="bulkUpdate" />
        <GalleryView :rows="rows" :columns="columns.visibleColumns.value" :fields="dt?.fields ?? []" :doctype="doctype"
          :image-field="dt?.image_field ?? undefined" :workspace="workspace" :is-loading="isLoading && !data"
          :selection="selection" />
        <ListPagination v-if="meta" :page="meta.page" :pages="meta.pages" :total="meta.total" :per-page="20"
          @update:page="page = $event" />
      </div>

      <template v-else>
        <BulkActionBar :count="selection.allSelected.value ? (meta?.total ?? 0) : selection.selectedIds.value.length"
          :total="meta?.total" :all-selected="selection.allSelected.value" :page-count="rows.length"
          :editable-fields="dt?.fields" @delete="bulkDelete" @clear="selection.clear"
          @select-all="selection.selectAllDocuments" @update="bulkUpdate" />

        <!-- List Content -->
        <div class="mt-2">
          <ListGroupedView v-if="groupBy && groupedRows" :dt="dt" :grouped-rows="groupedRows"
            :columns="columns.visibleColumns.value" :collapsed-groups="collapsedGroups" :sort-key="sortKey"
            :sort-order="sortOrder" :selection="selection" :group-by-field="groupByField"
            @toggle-group="(k) => collapsedGroups.has(k) ? collapsedGroups.delete(k) : collapsedGroups.add(k)"
            @sort="onSort" @select-all="selection.toggleAll(rows.map(r => String(r.id)))" @row-click="navigateToDoc"
            @inline-update="onInlineUpdate" />

          <template v-else>
            <div class="bg-card rounded-xl shadow-md ring-1 ring-border/60 overflow-hidden">
              <GruntDataTable :columns="columns.visibleColumns.value" :rows="rows" :fields="dt?.fields ?? []"
                :is-loading="isLoading && !data" :sort-key="sortKey" :sort-order="sortOrder"
                :selected-ids="selection.selectedIds.value" :all-selected="selection.allSelected.value"
                :status-config="dt?.status_config" :active-index="activeIndex" @sort="onSort" @select="selection.toggle"
                @select-all="selection.toggleAll(rows.map(r => String(r.id)))" @row-click="navigateToDoc"
                @inline-update="onInlineUpdate" />
            </div>
            <ListPagination v-if="meta" :page="meta.page" :pages="meta.pages" :total="meta.total" :per-page="20"
              @update:page="page = $event" class="mt-4" />
          </template>
        </div>
      </template>
    </div>
    <!-- Quick Entry Dialog -->
    <QuickEntryDialog v-if="showQuickEntry && dt" :dt="dt" :workspace="workspace" mode="list"
      @close="showQuickEntry = false" @saved="queryClient.invalidateQueries({ queryKey: ['documents', doctype] })" />

    <!-- Bulk delete progress dialog -->
    <Dialog :visible="deleteProgress.active" modal :closable="false" :show-header="false"
      :pt="{ root: { class: 'max-w-sm' }, content: { class: 'p-6' } }">
        <div class="flex flex-col gap-4 py-2">
          <div class="flex items-center gap-3">
            <div
              class="size-5 shrink-0 rounded-full border-2 border-destructive/20 border-t-destructive animate-spin" />
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
