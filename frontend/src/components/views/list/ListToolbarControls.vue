<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Search,
  Columns3,
  Rows3,
  Check,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
} from '@lucide/vue'
import draggable from 'vuedraggable'
import type { DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'

interface ListColumnsState {
  allAvailableColumns: { value: ListColumn[] }
  visibleColumns: { value: ListColumn[] }
  isCustomized: { value: boolean }
  isVisible: (key: string) => boolean
  toggleCol: (key: string) => void
  reorderCols: (oldIndex: number, newIndex: number) => void
}

const props = defineProps<{
  columns: ListColumnsState
  groupableFields: DocField[]
  groupBy: string | null
  groupByField: DocField | null
  sortKey: string
  sortOrder: 'asc' | 'desc'
  sortableColumns: ListColumn[]
}>()

const emit = defineEmits(['update:groupBy', 'sort'])

defineOptions({ inheritAttrs: false })

const opColumns = ref()
const opGrouping = ref()
const opSorting = ref()

const toggleColumns = (event: Event) => opColumns.value.toggle(event)
const toggleGrouping = (event: Event) => opGrouping.value.toggle(event)

const sortSearch = ref('')
const toggleSorting = (event: Event) => {
  sortSearch.value = ''
  opSorting.value.toggle(event)
}

function onColReorder(e: { oldIndex: number; newIndex: number }) {
  props.columns.reorderCols(e.oldIndex, e.newIndex)
}

const SYSTEM_SORT_OPTIONS = [
  { key: 'modified_at', label: 'Дата оновлення' },
  { key: 'created_at', label: 'Дата створення' },
  { key: 'name', label: 'Назва' },
]

const allSortOptions = computed(() => {
  const systemKeys = new Set(SYSTEM_SORT_OPTIONS.map((o) => o.key))
  const customOptions = props.sortableColumns
    .filter((c) => !systemKeys.has(c.key))
    .map((c) => ({ key: c.key, label: c.label }))
  return [...SYSTEM_SORT_OPTIONS, ...customOptions]
})

const filteredSortOptions = computed(() => {
  const q = sortSearch.value.trim().toLowerCase()
  if (!q) return allSortOptions.value
  return allSortOptions.value.filter((o) => o.label.toLowerCase().includes(q))
})

const activeSortLabel = computed(() =>
  props.sortKey
    ? (allSortOptions.value.find((o) => o.key === props.sortKey)?.label ?? props.sortKey)
    : null
)
</script>

<template>
<div class="contents">
  <!-- Columns -->
  <Button
    text size="small"
    class="h-9 px-2.5 gap-2 font-medium transition-all"
    :class="columns.isCustomized.value ? 'text-primary bg-primary/5' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
    @click="toggleColumns"
  >
    <Columns3 class="size-4" />
    <span class="hidden lg:inline">Стовпці</span>
    <Badge
      v-if="columns.isCustomized.value"
      severity="secondary"
      class="bg-primary/20 text-primary hover:bg-primary/20 size-5 p-0 flex items-center justify-center text-[10px]"
    >
      {{ columns.visibleColumns.value.length }}
    </Badge>
  </Button>

  <Popover ref="opColumns">
    <div class="w-64 p-1">
      <div class="px-2 py-1.5 flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-muted-foreground/80">
        <span>Стовпці</span>
        <span class="tabular-nums opacity-60">
          {{ columns.visibleColumns.value.length }}/{{ columns.allAvailableColumns.value.length }}
        </span>
      </div>
      <div class="h-px bg-border/40 my-1" />
      <div class="max-h-[320px] overflow-y-auto overflow-x-hidden scrollbar-none py-1">
        <draggable
          :model-value="columns.visibleColumns.value"
          item-key="key"
          handle=".drag-handle"
          class="space-y-0.5"
          @end="onColReorder"
        >
          <template #item="{ element: col }">
            <div
              class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group transition-colors"
              @click="columns.toggleCol(col.key)"
            >
              <span class="drag-handle cursor-grab text-muted-foreground/30 hover:text-muted-foreground select-none">⠿</span>
              <div class="size-4 flex items-center justify-center">
                <Check class="size-3.5 text-primary" />
              </div>
              <span class="flex-1 truncate text-sm font-medium">{{ col.label }}</span>
            </div>
          </template>
        </draggable>
        <div
          v-for="col in columns.allAvailableColumns.value.filter((c) => !columns.isVisible(c.key))"
          :key="col.key"
          class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group transition-colors"
          @click="columns.toggleCol(col.key)"
        >
          <span class="size-4" />
          <div class="size-4 flex items-center justify-center opacity-0 group-hover:opacity-30">
            <Check class="size-3.5" />
          </div>
          <span class="flex-1 truncate text-sm text-muted-foreground">{{ col.label }}</span>
        </div>
      </div>
    </div>
  </Popover>

  <!-- Group by -->
  <Button
    v-if="groupableFields.length"
    text size="small"
    class="h-9 px-2.5 gap-2 font-medium transition-all"
    :class="groupBy ? 'text-primary bg-primary/5' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
    @click="toggleGrouping"
  >
    <Rows3 class="size-4" />
    <span class="hidden lg:inline">{{ groupBy ? groupByField?.label : 'Групування' }}</span>
  </Button>

  <Popover ref="opGrouping">
    <div class="w-56 p-1">
      <div class="px-2 py-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground/80">Групувати за</div>
      <div class="h-px bg-border/40 my-1" />
      <div
        class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group transition-colors"
        @click="emit('update:groupBy', null); opGrouping.hide()"
      >
        <div class="size-4 flex items-center justify-center">
          <Check class="size-3.5 text-primary" :class="groupBy === null ? 'opacity-100' : 'opacity-0'" />
        </div>
        <span class="text-sm font-medium">Без групування</span>
      </div>
      <div class="h-px bg-border/40 my-1" />
      <div
        v-for="f in groupableFields"
        :key="f.fieldname"
        class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group transition-colors"
        @click="emit('update:groupBy', f.fieldname); opGrouping.hide()"
      >
        <div class="size-4 flex items-center justify-center">
          <Check class="size-3.5 text-primary" :class="groupBy === f.fieldname ? 'opacity-100' : 'opacity-0'" />
        </div>
        <span class="text-sm font-medium">{{ f.label }}</span>
      </div>
    </div>
  </Popover>

  <!-- Sort -->
  <Button
    text size="small"
    class="h-9 px-2.5 gap-2 font-medium transition-all"
    :class="sortKey ? 'text-primary bg-primary/5' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
    @click="toggleSorting"
  >
    <ArrowUpDown class="size-4" />
    <span class="hidden lg:inline">{{ activeSortLabel ?? 'Сортування' }}</span>
  </Button>

  <Popover ref="opSorting">
    <div class="w-64 p-1">
      <div class="px-2 py-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground/80">Сортувати за</div>
      <div class="h-px bg-border/40 my-1" />
      <div class="px-1 pb-1">
        <div class="relative group">
          <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground/50 group-focus-within:text-primary transition-colors" />
          <input
            v-model="sortSearch"
            class="w-full rounded-md border border-border/60 bg-muted/40 px-2 py-1.5 pl-8 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/30 transition-all"
            placeholder="Пошук поля..."
          />
        </div>
      </div>
      <div class="h-px bg-border/40 my-1" />
      <div
        class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer transition-colors"
        @click="emit('sort', ''); opSorting.hide()"
      >
        <div class="size-4 flex items-center justify-center">
          <Check class="size-3.5 text-primary" :class="!sortKey ? 'opacity-100' : 'opacity-0'" />
        </div>
        <span class="text-sm font-medium">За замовчуванням</span>
      </div>
      <div class="h-px bg-border/40 my-1" />
      <div v-if="!filteredSortOptions.length" class="px-2 py-3 text-sm text-center text-muted-foreground/60">Нічого не знайдено</div>
      <div class="max-h-[min(60vh,20rem)] overflow-y-auto pr-1">
        <div
          v-for="opt in filteredSortOptions"
          :key="opt.key"
          class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer transition-colors"
          @click="emit('sort', opt.key); opSorting.hide()"
        >
          <div class="size-4 flex items-center justify-center">
            <Check class="size-3.5 text-primary" :class="sortKey === opt.key ? 'opacity-100' : 'opacity-0'" />
          </div>
          <span class="flex-1 text-sm" :class="sortKey === opt.key ? 'font-semibold text-foreground' : ''">{{ opt.label }}</span>
          <component
            :is="sortOrder === 'asc' ? ArrowUp : ArrowDown"
            v-if="sortKey === opt.key"
            class="size-3.5 text-primary shrink-0"
          />
        </div>
      </div>
    </div>
  </Popover>
</div>
</template>
