<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useDocTypeStore } from '@/stores/doctype'
import { docsApi } from '@/core/api/docs'
import type { DocType, DocField } from '@/types'
import GButton from '@/components/ui/GButton.vue'
import GInput from '@/components/ui/GInput.vue'
import GSpinner from '@/components/ui/GSpinner.vue'
import GModal from '@/components/ui/GModal.vue'
import FilterBar from '@/components/views/FilterBar.vue'
import KanbanView from '@/components/views/KanbanView.vue'

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

// Use arrays instead of Set for Vue reactivity
const selectedIds = ref<string[]>([])
const hiddenCols = ref<string[]>([])

const showBulkDeleteModal = ref(false)
const showColMenu = ref(false)
const viewMode = ref<'list' | 'kanban'>('list')

// Kanban: first Select field that is in_list_view
const kanbanColumnField = computed<DocField | null>(() => {
  if (!dt.value) return null
  return dt.value.fields.find(
    (f: DocField) => f.fieldtype === 'Select' && f.in_list_view && !f.hidden
  ) ?? null
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
</script>

<template>
  <div class="p-8">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-semibold text-[--grunt-text-primary]">{{ dt?.label ?? doctype }}</h1>
      <div class="flex gap-2">
        <!-- View toggle: show Kanban only when a suitable Select field exists -->
        <template v-if="kanbanColumnField">
          <GButton
            :variant="viewMode === 'list' ? 'primary' : 'secondary'"
            size="sm"
            @click="viewMode = 'list'"
          >☰ Список</GButton>
          <GButton
            :variant="viewMode === 'kanban' ? 'primary' : 'secondary'"
            size="sm"
            @click="viewMode = 'kanban'"
          >⬛ Канбан</GButton>
        </template>
        <a
          :href="`/api/v1/docs/${doctype}/export/xlsx`"
          class="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium rounded-[--grunt-radius-sm] border border-[--grunt-border] text-[--grunt-text-secondary] hover:bg-[--grunt-surface-secondary] transition-colors"
          download
        >↓ Excel</a>
        <GButton @click="router.push(props.workspace ? `/${props.workspace}/list/${doctype}/new` : `/${doctype}/new`)">+ Новий</GButton>
      </div>
    </div>

    <!-- Kanban view -->
    <div v-if="viewMode === 'kanban' && kanbanColumnField && dt" class="h-[calc(100vh-12rem)]">
      <KanbanView :doctype="dt" :column-field="kanbanColumnField.fieldname" />
    </div>

    <template v-if="viewMode === 'list'">

    <div class="flex items-center gap-3 mb-2">
      <div class="w-72">
        <GInput v-model="search" placeholder="Пошук..." />
      </div>
      <div class="relative ml-auto">
        <button
          type="button"
          class="p-2 rounded border border-[--grunt-border] hover:bg-[--grunt-surface-secondary] text-[--grunt-text-secondary] text-sm"
          title="Колонки"
          @click="showColMenu = !showColMenu"
        >⚙</button>
        <div v-if="showColMenu" class="absolute right-0 top-full mt-1 bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-md] shadow-lg z-50 p-2 min-w-40">
          <label
            v-for="col in allColumns"
            :key="col.key"
            class="flex items-center gap-2 px-2 py-1 text-sm hover:bg-[--grunt-surface-secondary] rounded cursor-pointer"
          >
            <input type="checkbox" :checked="!hiddenCols.includes(col.key)" class="rounded" @change="toggleCol(col.key)" />
            {{ col.label }}
          </label>
        </div>
      </div>
    </div>

    <FilterBar v-if="dt" :fields="dt.fields" @change="onFiltersChange" />

    <div v-if="selectedIds.length > 0" class="flex items-center gap-3 mb-3 px-4 py-2 bg-[--grunt-primary-light] rounded-[--grunt-radius-md] border border-[--grunt-primary]/20">
      <span class="text-sm text-[--grunt-primary] font-medium">Вибрано: {{ selectedIds.length }}</span>
      <GButton variant="danger" size="sm" @click="showBulkDeleteModal = true">Видалити вибране</GButton>
      <button type="button" class="text-sm text-[--grunt-text-secondary] hover:text-[--grunt-text-primary] ml-auto" @click="clearSelection">Скасувати</button>
    </div>

    <div v-if="isLoading && !data" class="flex justify-center py-16">
      <GSpinner size="lg" />
    </div>

    <div v-else class="border border-[--grunt-border] rounded-[--grunt-radius-lg] overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-[--grunt-surface-secondary]">
          <tr>
            <th class="w-10 px-3 py-2.5 border-b border-[--grunt-border]">
              <input
                type="checkbox"
                :checked="rows.length > 0 && selectedIds.length === rows.length"
                class="rounded"
                @change="toggleSelectAll"
              />
            </th>
            <th
              v-for="col in visibleColumns"
              :key="col.key"
              class="text-left px-3 py-2.5 text-xs font-semibold text-[--grunt-text-secondary] border-b border-[--grunt-border] cursor-pointer hover:text-[--grunt-text-primary] select-none"
              @click="col.sortable && onSort(col.key)"
            >
              {{ col.label }}
              <span v-if="sortKey === col.key" class="ml-1">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="String(row.id)"
            class="border-b border-[--grunt-border] last:border-0 hover:bg-[--grunt-surface-secondary] cursor-pointer transition-colors"
            :class="{ 'bg-[--grunt-primary-light]/40': isSelected(String(row.id)) }"
          >
            <td class="px-3 py-2.5" @click.stop>
              <input type="checkbox" :checked="isSelected(String(row.id))" class="rounded" @change="toggleSelect(String(row.id))" />
            </td>
            <td
              v-for="col in visibleColumns"
              :key="col.key"
              class="px-3 py-2.5 text-[--grunt-text-primary]"
              @click="router.push(props.workspace ? `/${props.workspace}/list/${doctype}/${row.id}` : `/${doctype}/${row.id}`)"
            >{{ formatCell(row[col.key]) }}</td>
          </tr>
          <tr v-if="!rows.length && !isLoading">
            <td :colspan="visibleColumns.length + 1" class="px-3 py-8 text-center text-[--grunt-text-muted]">Записів не знайдено</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="meta && meta.pages > 1" class="mt-4 flex items-center justify-between text-sm text-[--grunt-text-secondary]">
      <span>Сторінка {{ meta.page }} з {{ meta.pages }} ({{ meta.total }} записів)</span>
      <div class="flex gap-2">
        <GButton variant="secondary" size="sm" :disabled="page <= 1" @click="page--">← Попередня</GButton>
        <GButton variant="secondary" size="sm" :disabled="page >= meta.pages" @click="page++">Наступна →</GButton>
      </div>
    </div>

    <GModal v-model="showBulkDeleteModal" title="Видалити вибрані записи?" size="sm">
      <p class="text-sm text-[--grunt-text-secondary]">Буде видалено {{ selectedIds.length }} записів. Цю дію не можна скасувати.</p>
      <template #footer>
        <GButton variant="secondary" @click="showBulkDeleteModal = false">Скасувати</GButton>
        <GButton variant="danger" @click="bulkDelete">Видалити</GButton>
      </template>
    </GModal>
    </template>
  </div>
</template>
