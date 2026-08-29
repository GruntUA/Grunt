<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  Search,
  SlidersHorizontal,
  Check,
  ArrowUp,
  ArrowDown,
} from '@lucide/vue'
import draggable from 'vuedraggable'
import type { DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { Button } from '@/components/ui/button'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
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

const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)
const activeTab = ref('columns')

const isCustomized = computed(() => props.columns.isCustomized.value || !!props.groupBy || !!props.sortKey)

const toggle = (event: Event) => {
  anchorEl.value = event.currentTarget as HTMLElement
  isOpen.value = !isOpen.value
}

const sortSearch = ref('')
watch(isOpen, (v) => { if (v) sortSearch.value = '' })

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
</script>

<template>
<div class="contents">
  <Tooltip>
    <TooltipTrigger as-child>
      <Button variant="ghost" size="icon" :class="isCustomized ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground'" @click="toggle">
        <SlidersHorizontal class="size-4" />
      </Button>
    </TooltipTrigger>
    <TooltipContent>Стовпці, групування, сортування</TooltipContent>
  </Tooltip>

  <Popover v-model:open="isOpen">
    <PopoverAnchor :reference="anchorEl ?? undefined" />
    <PopoverContent class="w-72 p-0">
      <Tabs v-model="activeTab" class="gap-0">
        <div class="p-1">
          <TabsList class="w-full">
            <TabsTrigger value="columns" class="flex-1">Стовпці</TabsTrigger>
            <TabsTrigger v-if="groupableFields.length" value="group" class="flex-1">Групування</TabsTrigger>
            <TabsTrigger value="sort" class="flex-1">Сортування</TabsTrigger>
          </TabsList>
        </div>

        <!-- Columns -->
        <TabsContent value="columns" class="p-1">
          <div class="px-2 py-1.5 flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>Видимі стовпці</span>
            <span class="tabular-nums">
              {{ columns.visibleColumns.value.length }}/{{ columns.allAvailableColumns.value.length }}
            </span>
          </div>
          <div class="max-h-[280px] overflow-y-auto overflow-x-hidden scrollbar-none py-1">
            <draggable
              :model-value="columns.visibleColumns.value"
              item-key="key"
              handle=".drag-handle"
              class="space-y-0.5"
              @end="onColReorder"
            >
              <template #item="{ element: col }">
                <div
                  class="flex items-center gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer"
                  @click="columns.toggleCol(col.key)"
                >
                  <span class="drag-handle cursor-grab text-muted-foreground select-none">⠿</span>
                  <Check class="size-4 shrink-0" />
                  <span class="flex-1 truncate">{{ col.label }}</span>
                </div>
              </template>
            </draggable>
            <div
              v-for="col in columns.allAvailableColumns.value.filter((c) => !columns.isVisible(c.key))"
              :key="col.key"
              class="flex items-center gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer"
              @click="columns.toggleCol(col.key)"
            >
              <span class="size-4" />
              <Check class="size-4 shrink-0 invisible" />
              <span class="flex-1 truncate text-muted-foreground">{{ col.label }}</span>
            </div>
          </div>
        </TabsContent>

        <!-- Group by -->
        <TabsContent v-if="groupableFields.length" value="group" class="p-1">
          <div class="px-2 py-1.5 text-xs font-medium text-muted-foreground">Групувати за</div>
          <div
            class="flex items-center gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer"
            @click="emit('update:groupBy', null)"
          >
            <Check class="size-4 shrink-0" :class="{ invisible: groupBy }" />
            <span>Без групування</span>
          </div>
          <Separator class="my-1" />
          <div class="max-h-[240px] overflow-y-auto scrollbar-none">
            <div
              v-for="f in groupableFields"
              :key="f.fieldname"
              class="flex items-center gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer"
              @click="emit('update:groupBy', f.fieldname)"
            >
              <Check class="size-4 shrink-0" :class="{ invisible: groupBy !== f.fieldname }" />
              <span>{{ f.label }}</span>
            </div>
          </div>
        </TabsContent>

        <!-- Sort -->
        <TabsContent value="sort" class="p-1">
          <div class="px-1 pb-1 pt-1">
            <div class="relative">
              <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
              <Input v-model="sortSearch" class="h-8 pl-8" placeholder="Пошук поля..." />
            </div>
          </div>
          <div
            class="flex items-center gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer"
            @click="emit('sort', '')"
          >
            <Check class="size-4 shrink-0" :class="{ invisible: sortKey }" />
            <span>За замовчуванням</span>
          </div>
          <Separator class="my-1" />
          <div v-if="!filteredSortOptions.length" class="px-2 py-3 text-center text-muted-foreground">Нічого не знайдено</div>
          <div class="max-h-[220px] overflow-y-auto pr-1">
            <div
              v-for="opt in filteredSortOptions"
              :key="opt.key"
              class="flex items-center gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer"
              @click="emit('sort', opt.key)"
            >
              <Check class="size-4 shrink-0" :class="{ invisible: sortKey !== opt.key }" />
              <span class="flex-1" :class="sortKey === opt.key ? 'font-medium' : ''">{{ opt.label }}</span>
              <component
                :is="sortOrder === 'asc' ? ArrowUp : ArrowDown"
                v-if="sortKey === opt.key"
                class="size-3.5 shrink-0"
              />
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </PopoverContent>
  </Popover>
</div>
</template>
