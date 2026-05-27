<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import type { DocType, DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import type { GroupedRowBucket } from '@/core/composables/useGrouping'
import GruntDataTable from '@/components/views/GruntDataTable.vue'
import BulkActionBar from '@/components/views/BulkActionBar.vue'
import ListGroupedView from '@/components/views/list/ListGroupedView.vue'

interface TableMeta {
  page: number
  pages: number
  total: number
}

interface SelectionState {
  selectedIds: string[]
  allSelected: boolean
  isSelected: (id: string) => boolean
  toggle: (id: string) => void
  toggleAll: (ids: string[]) => void
}

const props = defineProps<{
  dt: DocType | null
  workspace: string
  doctype: string
  rows: Record<string, unknown>[]
  columns: ListColumn[]
  fields: DocField[]
  meta: TableMeta | undefined
  isLoading: boolean
  sortKey: string | null
  sortOrder: 'asc' | 'desc'
  activeIndex: number
  fetchNextPage?: () => void
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  groupBy: string | null
  groupedRows: GroupedRowBucket[] | null
  collapsedGroups: Set<string>
  groupByField: DocField | null
  selection: SelectionState
  isSuperadmin?: boolean
}>()

const emit = defineEmits<{
  'sort': [key: string]
  'row-click': [row: Record<string, unknown>]
  'inline-update': [rowId: string, field: string, value: string]
  'delete': []
  'fast-delete': []
  'clear': []
  'select-all': []
  'update': [field: string, value: string]
  'toggle-group': [key: string]
}>()

const selectionCount = computed(() => props.selection.selectedIds.length)
const normalizedSortKey = computed(() => props.sortKey || '')

function rowDocId(row: Record<string, unknown>): string {
  return String(row.id ?? row.name ?? '')
}

const sentinelEl = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

function setupObserver() {
  observer?.disconnect()
  if (!sentinelEl.value || !props.fetchNextPage) return
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && props.hasNextPage && !props.isFetchingNextPage) {
        props.fetchNextPage?.()
      }
    },
    { rootMargin: '300px' },
  )
  observer.observe(sentinelEl.value)
}

onMounted(setupObserver)
onUnmounted(() => observer?.disconnect())
watch(() => sentinelEl.value, setupObserver)
</script>

<template>
  <div>
    <!-- Action Bar -->
    <BulkActionBar
      :count="selectionCount"
      :total="meta?.total"
      :all-selected="selection.allSelected"
      :page-count="rows?.length || 0"
      :editable-fields="dt?.fields"
      :is-superadmin="isSuperadmin"
      @delete="emit('delete')"
      @fast-delete="emit('fast-delete')"
      @clear="emit('clear')"
      @select-all="emit('select-all')"
      @update="(field, value) => emit('update', field, value)"
    />

    <!-- Total count — always visible above the table -->
    <div v-if="meta" class="flex items-center gap-2 mb-2 px-1">
      <span class="text-[11px] font-bold text-muted-foreground/60 uppercase tracking-widest">Всього:</span>
      <Badge severity="secondary" class="!text-[10px] !font-black !px-2 !py-0.5 shadow-sm">
        {{ meta.total }}
      </Badge>
      <span v-if="rows.length < meta.total" class="text-[11px] text-muted-foreground/50">
        (завантажено {{ rows.length }})
      </span>
    </div>

    <!-- List Content -->
    <div>
      <!-- Grouped View -->
      <ListGroupedView
        v-if="groupBy && groupedRows && dt && groupByField"
        :dt="dt"
        :workspace="workspace"
        :doctype="doctype"
        :grouped-rows="groupedRows"
        :columns="columns"
        :collapsed-groups="collapsedGroups"
        :sort-key="normalizedSortKey"
        :sort-order="sortOrder"
        :selection="selection"
        :group-by-field="groupByField"
        @toggle-group="(k) => emit('toggle-group', k)"
        @sort="(key) => emit('sort', key)"
        @select-all="selection.toggleAll(rows?.map((r) => rowDocId(r)).filter(Boolean) || [])"
        @row-click="(row) => emit('row-click', row)"
        @inline-update="(rowId, field, value) => emit('inline-update', rowId, field, value)"
      />

      <!-- Ungrouped List View -->
      <template v-else>
        <div class="bg-card rounded-xl shadow-md ring-1 ring-border/60 overflow-hidden">
          <GruntDataTable
            :columns="columns"
            :rows="rows"
            :fields="fields"
            :row-link-base="`/app/${workspace}/${doctype}`"
            :is-loading="isLoading"
            :sort-key="normalizedSortKey"
            :sort-order="sortOrder"
            :selected-ids="selection.selectedIds"
            :all-selected="selection.allSelected"
            :status-config="dt?.status_config"
            :active-index="activeIndex"
            @sort="(key) => emit('sort', key)"
            @select="(id) => selection.toggle(id)"
            @select-all="selection.toggleAll(rows.map((r) => rowDocId(r)).filter(Boolean))"
            @row-click="(row) => emit('row-click', row)"
            @inline-update="(rowId, field, value) => emit('inline-update', rowId, field, value)"
          />
        </div>
        <!-- Sentinel element — triggers next page load when scrolled into view -->
        <div ref="sentinelEl" class="h-1" aria-hidden="true" />

        <div v-if="isFetchingNextPage" class="flex justify-center py-4">
          <div class="size-5 rounded-full border-2 border-muted border-t-primary animate-spin" />
        </div>
        <p v-else-if="meta && !hasNextPage && rows.length > 0 && rows.length >= meta.total"
          class="py-3 text-center text-xs text-muted-foreground/50">
          Усі {{ meta.total }} записів завантажено
        </p>
      </template>
    </div>
  </div>
</template>
