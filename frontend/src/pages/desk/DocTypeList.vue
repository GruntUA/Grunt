<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useDocTypeStore } from '@/stores/doctype'
import { docsApi } from '@/core/api/docs'
import type { DocType, DocField } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Spinner } from '@/components/ui/spinner'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Search,
  Plus,
  Download,
  LayoutList,
  LayoutGrid,
  Settings2,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Trash2,
  ChevronLeft,
  ChevronRight,
  FileX,
} from 'lucide-vue-next'
import FilterBar from '@/components/views/FilterBar.vue'
import KanbanView from '@/components/views/KanbanView.vue'
import CalendarView from '@/components/views/CalendarView.vue'
import TreeView from '@/components/views/TreeView.vue'
import { CalendarDays as CalendarIcon, GitBranch } from 'lucide-vue-next'

const props = defineProps<{ doctype: string; workspace?: string }>()
const router = useRouter()
const dtStore = useDocTypeStore()
const queryClient = useQueryClient()

const dt = ref<DocType | null>(null)
const search = ref('')
const page = ref(1)
const sortKey = ref('')
const sortOrder = ref<'asc' | 'desc'>('asc')
const activeFilters = ref<Record<string, string>>({})

const selectedIds = ref<string[]>([])
const hiddenCols = ref<string[]>([])

const showBulkDeleteModal = ref(false)
const showColMenu = ref(false)
const viewMode = ref<'list' | 'kanban' | 'calendar' | 'tree'>('list')

const kanbanColumnField = computed<DocField | null>(() => {
  if (!dt.value) return null
  return dt.value.fields.find(
    (f: DocField) => f.fieldtype === 'Select' && f.in_list_view && !f.hidden
  ) ?? null
})

// Tree view: auto-detect self-referential Link field (e.g. parent points to same DocType)
const treeParentField = computed<DocField | null>(() => {
  if (!dt.value) return null
  // Explicit config wins
  if (dt.value.tree_view?.parent_field) {
    return dt.value.fields.find(f => f.fieldname === dt.value!.tree_view!.parent_field) ?? null
  }
  // Auto-detect: Link field whose options == this DocType (self-referential)
  return dt.value.fields.find(
    f => f.fieldtype === 'Link' && f.options === dt.value!.name
  ) ?? null
})

const calendarDateField = computed<DocField | null>(() => {
  if (!dt.value) return null
  if (dt.value.calendar_view?.field) {
    const fieldname = dt.value.calendar_view.field
    return dt.value.fields.find(f => f.fieldname === fieldname) || null
  }
  return dt.value.fields.find(f => f.fieldtype === 'Date' || f.fieldtype === 'Datetime') || null
})

const debouncedSearch = ref('')
let debounceTimer: ReturnType<typeof setTimeout>
watch(search, (v) => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debouncedSearch.value = v; page.value = 1 }, 400)
})

onMounted(async () => {
  dt.value = await dtStore.get(props.doctype)
  const saved = localStorage.getItem(`grunt_columns_${props.doctype}`)
  if (saved) hiddenCols.value = JSON.parse(saved) as string[]
})

const allColumns = computed(() => {
  const base = (dt.value?.fields ?? [])
    .filter((f: DocField) => f.in_list_view && !f.hidden)
    .map((f: DocField) => ({ key: f.fieldname, label: f.label, sortable: true }))
  return base.length ? base : [{ key: 'name', label: 'Назва', sortable: true }, { key: 'created_at', label: 'Створено', sortable: false }]
})

const visibleColumns = computed(() => allColumns.value.filter((c) => !hiddenCols.value.includes(c.key)))

function toggleCol(key: string) {
  if (hiddenCols.value.includes(key)) {
    hiddenCols.value = hiddenCols.value.filter((k) => k !== key)
  } else {
    hiddenCols.value = [...hiddenCols.value, key]
  }
  localStorage.setItem(`grunt_columns_${props.doctype}`, JSON.stringify(hiddenCols.value))
}

const { data, isLoading } = useQuery({
  queryKey: computed(() => ['documents', props.doctype, page.value, debouncedSearch.value, sortKey.value, sortOrder.value, JSON.stringify(activeFilters.value)]),
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

function onSort(key: string) {
  sortOrder.value = sortKey.value === key && sortOrder.value === 'asc' ? 'desc' : 'asc'
  sortKey.value = key
}

function isSelected(id: string) {
  return selectedIds.value.includes(id)
}

function toggleSelect(id: string) {
  if (isSelected(id)) {
    selectedIds.value = selectedIds.value.filter((s) => s !== id)
  } else {
    selectedIds.value = [...selectedIds.value, id]
  }
}

function toggleSelectAll() {
  if (selectedIds.value.length === rows.value.length) {
    selectedIds.value = []
  } else {
    selectedIds.value = rows.value.map((r) => String(r.id))
  }
}

function clearSelection() {
  selectedIds.value = []
}

async function bulkDelete() {
  for (const id of selectedIds.value) {
    try { await docsApi.delete(props.doctype, id) } catch {}
  }
  selectedIds.value = []
  showBulkDeleteModal.value = false
  queryClient.invalidateQueries({ queryKey: ['documents', props.doctype] })
}

function formatCell(val: unknown): string {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'boolean') return val ? '✓' : ''
  return String(val)
}

function onFiltersChange(f: Record<string, string>) {
  activeFilters.value = f
  page.value = 1
}

const isSystemDocType = computed(() => props.doctype === 'DocType')

function navigateToDoc(row: Record<string, unknown>) {
  // System DocTypes: open the builder instead of a form
  if (isSystemDocType.value) {
    router.push(`/studio/${row.name}/builder`)
    return
  }
  const id = String(row.id)
  router.push(props.workspace ? `/${props.workspace}/list/${props.doctype}/${id}` : `/${props.doctype}/${id}`)
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
        <!-- View toggle -->
        <div v-if="kanbanColumnField || treeParentField" class="flex rounded-lg border border-border overflow-hidden">
          <button
            class="px-3 py-1.5 text-sm font-medium transition-colors flex items-center gap-1.5"
            :class="viewMode === 'list' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground'"
            @click="viewMode = 'list'"
          >
            <LayoutList class="size-4" />
            Список
          </button>
          <button
            v-if="kanbanColumnField"
            class="px-3 py-1.5 text-sm font-medium transition-colors flex items-center gap-1.5 border-l border-border"
            :class="viewMode === 'kanban' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground'"
            @click="viewMode = 'kanban'"
          >
            <LayoutGrid class="size-4" />
            Канбан
          </button>
          <button
            v-if="calendarDateField"
            class="px-3 py-1.5 text-sm font-medium transition-colors flex items-center gap-1.5 border-l border-border"
            :class="viewMode === 'calendar' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground'"
            @click="viewMode = 'calendar'"
          >
            <CalendarIcon class="size-4" />
            Календар
          </button>
          <button
            v-if="treeParentField"
            class="px-3 py-1.5 text-sm font-medium transition-colors flex items-center gap-1.5 border-l border-border"
            :class="viewMode === 'tree' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground'"
            @click="viewMode = 'tree'"
          >
            <GitBranch class="size-4" />
            Дерево
          </button>
        </div>

        <Button v-if="!isSystemDocType" variant="outline" size="sm" as="a" :href="`/api/v1/docs/${doctype}/export/xlsx`" download>
          <Download class="size-4 mr-1.5" />
          Excel
        </Button>
        <Button v-if="isSystemDocType" size="sm" @click="router.push('/studio')">
          <Plus class="size-4 mr-1.5" />
          Новий DocType
        </Button>
        <Button v-else size="sm" @click="router.push(props.workspace ? `/${props.workspace}/list/${doctype}/new` : `/${doctype}/new`)">
          <Plus class="size-4 mr-1.5" />
          Новий
        </Button>
      </div>
    </div>

    <!-- Kanban view -->
    <div v-if="viewMode === 'kanban' && kanbanColumnField && dt" class="h-[calc(100vh-12rem)]">
      <KanbanView :doctype="dt" :column-field="kanbanColumnField.fieldname" />
    </div>

    <!-- Calendar view -->
    <div v-if="viewMode === 'calendar' && calendarDateField && dt" class="h-[calc(100vh-12rem)]">
      <CalendarView :doctype="dt" :date-field="calendarDateField.fieldname" :workspace="workspace" />
    </div>

    <!-- Tree view -->
    <div v-if="viewMode === 'tree' && treeParentField && dt">
      <TreeView :doctype="dt" :parent-field="treeParentField.fieldname" :workspace="workspace" />
    </div>

    <template v-if="viewMode === 'list'">
      <!-- Search + column settings -->
      <div class="flex items-center gap-3 mb-3">
        <div class="relative w-72">
          <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
          <Input v-model="search" placeholder="Пошук..." class="pl-9" />
        </div>

        <div class="ml-auto">
          <DropdownMenu v-model:open="showColMenu">
            <DropdownMenuTrigger as-child>
              <Button variant="ghost" size="icon-sm" title="Колонки">
                <Settings2 class="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="p-2 min-w-40">
              <label
                v-for="col in allColumns"
                :key="col.key"
                class="flex items-center gap-2 px-2 py-1.5 text-sm hover:bg-accent rounded-md cursor-pointer transition-colors"
              >
                <Checkbox
                  :checked="!hiddenCols.includes(col.key)"
                  @update:checked="toggleCol(col.key)"
                />
                {{ col.label }}
              </label>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <!-- Filters -->
      <FilterBar v-if="dt" :fields="dt.fields" @change="onFiltersChange" />

      <!-- Bulk action bar -->
      <Transition name="bulk">
        <div v-if="selectedIds.length > 0" class="flex items-center gap-3 mb-3 px-4 py-2.5 bg-primary/5 rounded-lg border border-primary/20">
          <span class="text-sm text-primary font-medium">Вибрано: {{ selectedIds.length }}</span>
          <Button variant="destructive" size="sm" @click="showBulkDeleteModal = true">
            <Trash2 class="size-3.5 mr-1" />
            Видалити
          </Button>
          <button type="button" class="text-sm text-muted-foreground hover:text-foreground ml-auto transition-colors" @click="clearSelection">Скасувати</button>
        </div>
      </Transition>

      <!-- Loading -->
      <div v-if="isLoading && !data" class="flex justify-center py-16">
        <Spinner size="lg" />
      </div>

      <!-- Table -->
      <div v-else class="border border-border rounded-lg overflow-hidden bg-card shadow-sm">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-border bg-muted/50">
              <th class="w-10 px-3 py-3">
                <Checkbox
                  :checked="rows.length > 0 && selectedIds.length === rows.length"
                  @update:checked="toggleSelectAll"
                />
              </th>
              <th
                v-for="col in visibleColumns"
                :key="col.key"
                class="text-left px-3 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground select-none transition-colors"
                :class="{ 'cursor-pointer hover:text-foreground': col.sortable }"
                @click="col.sortable && onSort(col.key)"
              >
                <span class="inline-flex items-center gap-1">
                  {{ col.label }}
                  <ArrowUp v-if="sortKey === col.key && sortOrder === 'asc'" class="size-3.5" />
                  <ArrowDown v-else-if="sortKey === col.key && sortOrder === 'desc'" class="size-3.5" />
                  <ArrowUpDown v-else-if="col.sortable" class="size-3.5 opacity-0 group-hover:opacity-30" />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="String(row.id)"
              class="border-b border-border last:border-0 hover:bg-muted/30 cursor-pointer transition-colors group"
              :class="{ 'bg-primary/5': isSelected(String(row.id)) }"
            >
              <td class="px-3 py-3" @click.stop>
                <Checkbox
                  :checked="isSelected(String(row.id))"
                  @update:checked="toggleSelect(String(row.id))"
                />
              </td>
              <td
                v-for="(col, ci) in visibleColumns"
                :key="col.key"
                class="px-3 py-3"
                :class="ci === 0 ? 'font-medium text-foreground' : 'text-muted-foreground'"
                @click="navigateToDoc(row)"
              >{{ formatCell(row[col.key]) }}</td>
            </tr>
            <!-- Empty state -->
            <tr v-if="!rows.length && !isLoading">
              <td :colspan="visibleColumns.length + 1" class="px-3 py-16 text-center">
                <div class="flex flex-col items-center gap-2">
                  <FileX class="size-10 text-muted-foreground/40" />
                  <p class="text-sm text-muted-foreground">Записів не знайдено</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div v-if="meta && meta.pages > 1" class="mt-4 flex items-center justify-between">
        <p class="text-sm text-muted-foreground">
          {{ (meta.page - 1) * 20 + 1 }}–{{ Math.min(meta.page * 20, meta.total) }} з {{ meta.total }}
        </p>
        <div class="flex items-center gap-1">
          <Button variant="outline" size="icon-sm" :disabled="page <= 1" @click="page--">
            <ChevronLeft class="size-4" />
          </Button>
          <span class="px-3 text-sm text-muted-foreground">{{ meta.page }} / {{ meta.pages }}</span>
          <Button variant="outline" size="icon-sm" :disabled="page >= meta.pages" @click="page++">
            <ChevronRight class="size-4" />
          </Button>
        </div>
      </div>

      <!-- Bulk delete dialog -->
      <AlertDialog :open="showBulkDeleteModal" @update:open="showBulkDeleteModal = $event">
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Видалити вибрані записи?</AlertDialogTitle>
            <AlertDialogDescription>Буде видалено {{ selectedIds.length }} записів. Цю дію не можна скасувати.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Скасувати</AlertDialogCancel>
            <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90" @click="bulkDelete">Видалити</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </template>
  </div>
</template>

<style scoped>
.bulk-enter-active,
.bulk-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}
.bulk-enter-from,
.bulk-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
