<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useDocTypeStore } from '@/stores/doctype'
import { useAuthStore } from '@/stores/auth'
import { useListSelection } from '@/core/composables/useListSelection'
import { useListColumns } from '@/core/composables/useListColumns'
import { useDevMode } from '@/core/composables/useDevMode'
import { docsApi } from '@/core/api/docs'
import type { DocType, DocField } from '@/types'
import { Button } from '@/components/ui/button'
import { Download, Plus, Search, Columns3, X, LayoutList, LayoutGrid, CalendarDays, GitBranch, Pencil, MoreHorizontal, Rows3, ChevronRight, Check, FileBarChart } from 'lucide-vue-next'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import FilterBar from '@/components/views/FilterBar.vue'
import BulkActionBar from '@/components/views/BulkActionBar.vue'
import DataTable from '@/components/views/DataTable.vue'
import ListPagination from '@/components/views/ListPagination.vue'
import KanbanView from '@/components/views/KanbanView.vue'
import CalendarView from '@/components/views/CalendarView.vue'
import TreeView from '@/components/views/TreeView.vue'

const props = defineProps<{ doctype: string; workspace?: string }>()
const router = useRouter()
const route = useRoute()
const dtStore = useDocTypeStore()
const auth = useAuthStore()
const queryClient = useQueryClient()
const { isDev } = useDevMode()

const dt = ref<DocType | null>(null)
const page = ref(1)
const debouncedSearch = ref('')
const sortKey = ref('')
const sortOrder = ref<'asc' | 'desc'>('asc')
const activeFilters = ref<Record<string, string>>({})
type ViewMode = 'list' | 'kanban' | 'calendar' | 'tree'
const VALID_VIEWS: ViewMode[] = ['list', 'kanban', 'calendar', 'tree']

const viewMode = ref<ViewMode>('list')
const inlineSearch = ref('')
const showColMenu = ref(false)
const groupBy = ref<string | null>(null)
const collapsedGroups = ref<Set<string>>(new Set())

let searchDebounce: ReturnType<typeof setTimeout>
watch(inlineSearch, (v) => {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => { debouncedSearch.value = v; page.value = 1 }, 400)
})

const selection = useListSelection()
const columns = useListColumns(props.doctype, () => dt.value?.fields ?? [])

// ── Grouping ─────────────────────────────────────────────────────────

const NON_GROUPABLE = new Set([
  'Section', 'Column', 'Tab', 'Table', 'MultiLink',
  'RichText', 'JSON', 'Code', 'LongText', 'Attach', 'Image', 'Signature', 'Geolocation',
])

const groupableFields = computed(() => {
  if (!dt.value) return []
  return dt.value.fields.filter(
    (f: DocField) => !NON_GROUPABLE.has(f.fieldtype) && !f.hidden && (f.in_list_view || f.in_filter),
  )
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

const groupByField = computed(() =>
  groupableFields.value.find(f => f.fieldname === groupBy.value) ?? null,
)

function groupLabel(key: string): string {
  if (!key) return '—'
  if (groupByField.value?.fieldtype === 'Check') return key === '1' || key === 'true' ? 'Так' : 'Ні'
  return key
}

function toggleGroup(key: string) {
  const next = new Set(collapsedGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsedGroups.value = next
}

function setGroupBy(field: string | null) {
  groupBy.value = field
  collapsedGroups.value = new Set()
  page.value = 1
  const query = { ...route.query }
  if (field) {
    query.groupBy = field
  } else {
    delete query.groupBy
  }
  router.replace({ query })
}

onMounted(async () => {
  dt.value = await dtStore.get(props.doctype)

  // Determine initial view: URL param → doctype default → 'list'
  const urlView = route.query.view as string | undefined
  const defaultView = dt.value?.default_view ?? 'list'
  const initial = (VALID_VIEWS.includes(urlView as ViewMode) ? urlView : defaultView) as ViewMode
  viewMode.value = initial

  // Restore groupBy from URL
  const urlGroupBy = route.query.groupBy as string | undefined
  if (urlGroupBy) groupBy.value = urlGroupBy

  // Restore sort from URL
  const urlSort = route.query.sort as string | undefined
  const urlOrder = route.query.order as string | undefined
  if (urlSort) sortKey.value = urlSort
  if (urlOrder === 'asc' || urlOrder === 'desc') sortOrder.value = urlOrder
})

// Sync viewMode → URL query param
watch(viewMode, (v) => {
  const defaultView = dt.value?.default_view ?? 'list'
  const query = { ...route.query }
  if (v === defaultView) {
    delete query.view
  } else {
    query.view = v
  }
  router.replace({ query })
})

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

const SYSTEM_DATE_FIELDNAMES = new Set(['created_at', 'modified_at'])

const calendarDateField = computed<DocField | null>(() => {
  if (!dt.value) return null
  if (dt.value.calendar_view?.field) {
    const fieldname = dt.value.calendar_view.field
    // System date fields are not in dt.fields but are valid — return a synthetic DocField
    if (SYSTEM_DATE_FIELDNAMES.has(fieldname)) {
      return { fieldname, fieldtype: 'Datetime', label: fieldname } as DocField
    }
    return dt.value.fields.find(f => f.fieldname === fieldname) ?? null
  }
  return dt.value.fields.find(f => f.fieldtype === 'Date' || f.fieldtype === 'Datetime') ?? null
})


// ── Data fetching ────────────────────────────────────────────────────

const { data, isLoading } = useQuery({
  queryKey: computed(() => [
    'documents', props.doctype, page.value, debouncedSearch.value,
    sortKey.value, sortOrder.value, JSON.stringify(activeFilters.value),
    groupBy.value,
  ]),
  queryFn: () => docsApi.list(props.doctype, {
    page: page.value,
    per_page: groupBy.value ? 100 : 20,
    search: debouncedSearch.value || undefined,
    sort: groupBy.value ?? sortKey.value ?? undefined,
    order: groupBy.value ? 'asc' : (sortKey.value ? sortOrder.value : undefined),
    filters: activeFilters.value,
  }),
  refetchOnMount: 'always',
})

const meta = computed(() => data.value?.meta)
const rows = computed(() => (data.value?.data ?? []) as Record<string, unknown>[])

// ── Event handlers ───────────────────────────────────────────────────

function onSort(key: string) {
  sortOrder.value = sortKey.value === key && sortOrder.value === 'asc' ? 'desc' : 'asc'
  sortKey.value = key
  const query = { ...route.query, sort: key, order: sortOrder.value }
  router.replace({ query })
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
      per_page: 10000,
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

const showDevActions = computed(() => isDev && auth.user?.is_superadmin)

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
  <div class="flex flex-1 flex-col gap-4 sm:gap-6 p-4 sm:p-6 lg:p-8">
    <!-- Title row -->
    <div class="flex flex-wrap items-end justify-between gap-2">
      <div>
        <h2 class="text-2xl font-bold tracking-tight text-foreground">{{ dt?.label ?? doctype }}</h2>
        <p class="text-muted-foreground font-medium text-sm">
          {{ meta ? `${meta.total} ${meta.total === 1 ? 'запис' : 'записів'}` : '\u00a0' }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <!-- Actions menu -->
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm" class="text-foreground h-9 w-9 p-0">
              <MoreHorizontal class="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-52">
            <DropdownMenuItem v-if="!isSystemDocType" as="a"
              :href="`/api/v1/docs/${doctype}/export/xlsx?token=${auth.token}`" download>
              <Download class="size-4" />
              Завантажити Excel
            </DropdownMenuItem>
            <template v-if="showDevActions">
              <DropdownMenuSeparator v-if="!isSystemDocType" />
              <DropdownMenuItem @click="router.push(`/${workspace ?? 'grunt'}/list/DocType/${doctype}`)">
                <Pencil class="size-4" />
                Редагувати доктайп
              </DropdownMenuItem>
            </template>
            <DropdownMenuSeparator />
            <DropdownMenuItem @click="router.push({ name: 'report-builder', params: { workspaceName: workspace ?? 'grunt' }, query: { doctype: doctype } })">
              <FileBarChart class="size-4" />
              Створити звіт
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <!-- New button -->
        <Button v-if="isSystemDocType" size="sm" @click="router.push(`/${workspace ?? 'grunt'}/list/DocType/new`)">
          <Plus class="size-4 mr-1.5" />
          Новий DocType
        </Button>
        <Button v-else size="sm"
          @click="router.push(workspace ? `/${workspace}/list/${doctype}/new` : `/${doctype}/new`)">
          <Plus class="size-4 mr-1.5" />
          Новий
        </Button>
      </div>
    </div>

    <!-- Toolbar (always visible) -->
    <div class="flex items-center justify-between gap-2">
      <!-- Left: search + filters (list mode only) -->
      <div v-if="viewMode === 'list'"
        class="flex flex-1 flex-col-reverse items-start gap-y-2 sm:flex-row sm:items-center sm:space-x-2">
        <div class="relative w-[150px] lg:w-[250px]">
          <Search
            class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/80 pointer-events-none" />
          <input v-model="inlineSearch" placeholder="Пошук..."
            class="flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 pl-8 text-sm text-foreground transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
        </div>
        <FilterBar v-if="dt" :fields="dt.fields" @change="onFiltersChange" class="!mb-0" />
        <Button v-if="inlineSearch || Object.keys(activeFilters).length" variant="ghost" size="sm"
          class="h-8 px-2 lg:px-3" @click="inlineSearch = ''; debouncedSearch = ''; activeFilters = {}; page = 1">
          Скинути
          <X class="ml-2 size-4" />
        </Button>
      </div>
      <div v-else class="flex-1" />

      <!-- Right: columns + view switcher -->
      <div class="flex items-center gap-2">
        <!-- Columns dropdown (list mode only) -->
        <DropdownMenu v-if="viewMode === 'list'" v-model:open="showColMenu">
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm" class="h-8" :class="columns.isCustomized.value
              ? 'text-primary border-primary/40 bg-primary/5'
              : 'text-foreground'">
              <Columns3 class="mr-2 size-4" />
              Стовпці
              <span v-if="columns.isCustomized.value"
                class="ml-1.5 rounded-full bg-primary/15 px-1.5 py-px text-[10px] font-medium leading-none text-primary tabular-nums">
                {{ columns.visibleColumns.value.length }}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-48">
            <DropdownMenuLabel class="flex items-center justify-between">
              <span>Видимі стовпці</span>
              <span class="text-xs font-normal text-muted-foreground tabular-nums">
                {{ columns.visibleColumns.value.length }}/{{ columns.allAvailableColumns.value.length }}
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem v-for="col in columns.allAvailableColumns.value" :key="col.key" class="gap-2"
              @select.prevent="columns.toggleCol(col.key)">
              <Check class="size-3.5 shrink-0"
                :class="columns.isVisible(col.key) ? 'opacity-100 text-primary' : 'opacity-0'" />
              {{ col.label }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <!-- Group by dropdown (list mode only) -->
        <DropdownMenu v-if="viewMode === 'list' && groupableFields.length">
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm" class="h-8"
              :class="groupBy ? 'text-primary border-primary/40 bg-primary/5' : 'text-foreground'">
              <Rows3 class="mr-2 size-4" />
              {{ groupBy ? groupByField?.label : 'Групування' }}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-52">
            <DropdownMenuLabel>Групувати за</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem class="gap-2" @click="setGroupBy(null)">
              <Check class="size-3.5" :class="groupBy === null ? 'opacity-100' : 'opacity-0'" />
              Без групування
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem v-for="f in groupableFields" :key="f.fieldname" class="gap-2"
              @click="setGroupBy(f.fieldname)">
              <Check class="size-3.5" :class="groupBy === f.fieldname ? 'opacity-100' : 'opacity-0'" />
              {{ f.label }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <!-- View mode switcher -->
        <div class="flex items-center rounded-md border border-input overflow-hidden">
          <button type="button" class="h-8 px-2.5 flex items-center transition-colors"
            :class="viewMode === 'list' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
            title="Список" @click="viewMode = 'list'">
            <LayoutList class="size-4" />
          </button>
          <button v-if="kanbanColumnField" type="button"
            class="h-8 px-2.5 flex items-center border-l border-input transition-colors"
            :class="viewMode === 'kanban' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
            title="Канбан" @click="viewMode = 'kanban'">
            <LayoutGrid class="size-4" />
          </button>
          <button v-if="calendarDateField" type="button"
            class="h-8 px-2.5 flex items-center border-l border-input transition-colors"
            :class="viewMode === 'calendar' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
            title="Календар" @click="viewMode = 'calendar'">
            <CalendarDays class="size-4" />
          </button>
          <button v-if="treeParentField" type="button"
            class="h-8 px-2.5 flex items-center border-l border-input transition-colors"
            :class="viewMode === 'tree' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
            title="Дерево" @click="viewMode = 'tree'">
            <GitBranch class="size-4" />
          </button>
        </div>
      </div>
    </div>

    <!-- Views -->
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
      <BulkActionBar :count="selection.allSelected.value ? (meta?.total ?? 0) : selection.selectedIds.value.length"
        :total="meta?.total" :all-selected="selection.allSelected.value" :page-count="rows.length" @delete="bulkDelete"
        @clear="selection.clear" @select-all="selection.selectAllDocuments" />

      <!-- Grouped view -->
      <template v-if="groupBy && groupedRows">
        <!-- Shared column header -->
        <DataTable :columns="columns.visibleColumns.value" :rows="[]" :fields="dt?.fields ?? []" :is-loading="false"
          :sort-key="sortKey" :sort-order="sortOrder" :selected-ids="[]" :status-config="dt?.status_config"
          :hide-body="true" @sort="onSort" @select="() => { }" @select-all="onSelectAll" @row-click="() => { }" />
        <!-- Groups -->
        <div v-for="group in groupedRows" :key="group.key" class="rounded-md border border-border overflow-hidden">
          <!-- Group header -->
          <button type="button"
            class="w-full flex items-center gap-2.5 px-4 py-2.5 bg-muted/50 hover:bg-muted text-sm font-medium transition-colors text-left"
            @click="toggleGroup(group.key)">
            <ChevronRight class="size-3.5 text-muted-foreground shrink-0 transition-transform duration-150"
              :class="!collapsedGroups.has(group.key) && 'rotate-90'" />
            <span class="text-foreground">{{ groupLabel(group.key) }}</span>
            <span
              class="ml-auto text-xs text-muted-foreground tabular-nums bg-background border border-border px-2 py-0.5 rounded-full">
              {{ group.items.length }}
            </span>
          </button>
          <!-- Group rows -->
          <DataTable v-if="!collapsedGroups.has(group.key)" :columns="columns.visibleColumns.value" :rows="group.items"
            :fields="dt?.fields ?? []" :is-loading="false" :sort-key="sortKey" :sort-order="sortOrder"
            :selected-ids="selection.selectedIds.value" :all-selected="selection.allSelected.value"
            :status-config="dt?.status_config" :hide-header="true" @sort="onSort" @select="selection.toggle"
            @select-all="() => selection.toggleAll(group.items.map(r => String(r.id)))" @row-click="navigateToDoc" />
        </div>
      </template>

      <!-- Normal (ungrouped) view -->
      <template v-else>
        <DataTable :columns="columns.visibleColumns.value" :rows="rows" :fields="dt?.fields ?? []"
          :is-loading="isLoading && !data" :sort-key="sortKey" :sort-order="sortOrder"
          :selected-ids="selection.selectedIds.value" :all-selected="selection.allSelected.value"
          :status-config="dt?.status_config" @sort="onSort" @select="selection.toggle" @select-all="onSelectAll"
          @row-click="navigateToDoc" />

        <ListPagination v-if="meta" :page="meta.page" :pages="meta.pages" :total="meta.total" :per-page="20"
          @update:page="page = $event" />
      </template>
    </template>
  </div>
</template>
