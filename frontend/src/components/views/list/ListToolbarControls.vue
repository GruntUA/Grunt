<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, watch } from 'vue'
import {
  Search,
  SlidersHorizontal,
  Check,
  ArrowUp,
  ArrowDown,
  GripVertical,
  Plus,
  X,
  RotateCcw,
  Columns3,
  Rows3,
  ArrowUpDown,
} from '@lucide/vue'
import { VueDraggable } from 'vue-draggable-plus'
import type { DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Input } from '@/components/ui/input'

const { t } = useI18n()
interface ListColumnsState {
  allAvailableColumns: { value: ListColumn[] }
  visibleColumns: { value: ListColumn[] }
  isCustomized: { value: boolean }
  isVisible: (key: string) => boolean
  toggleCol: (key: string) => void
  reorderCols: (oldIndex: number, newIndex: number) => void
  setVisibleKeys?: (keys: string[]) => void
  resetCols?: () => void
}

const props = defineProps<{
  columns: ListColumnsState
  groupableFields: DocField[]
  groupBy: string | null
  groupByField: DocField | null
  sortKey: string
  sortOrder: 'asc' | 'desc'
  sortableColumns: ListColumn[]
  defaultSortKey?: string
  defaultSortOrder?: 'asc' | 'desc'
}>()

const emit = defineEmits(['update:groupBy', 'sort'])

defineOptions({ inheritAttrs: false })

const isOpen = ref(false)
const activeTab = ref('columns')

const isCustomized = computed(() => props.columns.isCustomized.value || !!props.groupBy || !!props.sortKey)

const colSearch = ref('')
const groupSearch = ref('')
const sortSearch = ref('')
watch(isOpen, (v) => {
  if (v) {
    colSearch.value = ''
    groupSearch.value = ''
    sortSearch.value = ''
  }
})

const matches = (label: string, q: string) => label.toLowerCase().includes(q.trim().toLowerCase())

// ── Columns ──────────────────────────────────────────────

const hiddenColumns = computed(() =>
  props.columns.allAvailableColumns.value.filter((c) => !props.columns.isVisible(c.key)),
)
const filteredHiddenColumns = computed(() =>
  hiddenColumns.value.filter((c) => matches(c.label, colSearch.value)),
)
// Keep at least one column visible
const canHide = computed(() => props.columns.visibleColumns.value.length > 1)

function onColReorder(e: { oldIndex?: number; newIndex?: number }) {
  if (e.oldIndex == null || e.newIndex == null) return
  props.columns.reorderCols(e.oldIndex, e.newIndex)
}

function showAllCols() {
  if (!props.columns.setVisibleKeys) {
    hiddenColumns.value.forEach((c) => props.columns.toggleCol(c.key))
    return
  }
  props.columns.setVisibleKeys([
    ...props.columns.visibleColumns.value.map((c) => c.key),
    ...hiddenColumns.value.map((c) => c.key),
  ])
}

// ── Grouping ─────────────────────────────────────────────

const filteredGroupFields = computed(() =>
  props.groupableFields.filter((f) => matches(f.label, groupSearch.value)),
)

// ── Sorting ──────────────────────────────────────────────

const SYSTEM_SORT_OPTIONS = [
  { key: 'modified_at', label: t('Last updated') },
  { key: 'created_at', label: t('Created on') },
  { key: 'name', label: t('Name') },
]

const allSortOptions = computed(() => {
  const systemKeys = new Set(SYSTEM_SORT_OPTIONS.map((o) => o.key))
  const customOptions = props.sortableColumns
    .filter((c) => !systemKeys.has(c.key))
    .map((c) => ({ key: c.key, label: c.label }))
  return [...SYSTEM_SORT_OPTIONS, ...customOptions]
})

const filteredSortOptions = computed(() =>
  allSortOptions.value.filter((o) => matches(o.label, sortSearch.value)),
)

// No explicit sort -> the list uses the DocType default (sort_field / sort_order)
const effectiveSortKey = computed(() => props.sortKey || props.defaultSortKey || '')
const effectiveSortOrder = computed(() =>
  props.sortKey ? props.sortOrder : (props.defaultSortOrder ?? 'desc'),
)

// applySort toggles direction when the same key is sent again; from the
// default state the first emit pins the key with 'asc'
function setSortOrder(order: 'asc' | 'desc') {
  const key = effectiveSortKey.value
  if (!key || effectiveSortOrder.value === order) return
  emit('sort', key)
  if (!props.sortKey && order === 'desc') emit('sort', key)
}

function resetAll() {
  props.columns.resetCols?.()
  emit('update:groupBy', null)
  emit('sort', '')
}

const rowClass = 'group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent hover:text-accent-foreground'
</script>

<template>
<div class="contents">
  <Tooltip>
    <TooltipTrigger as-child>
      <Button variant="ghost" size="icon" :class="isCustomized ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground'" @click="isOpen = true">
        <SlidersHorizontal class="size-4" />
      </Button>
    </TooltipTrigger>
    <TooltipContent>{{ t('Columns, grouping, sorting') }}</TooltipContent>
  </Tooltip>

  <Dialog v-model:open="isOpen">
    <DialogContent class="flex max-h-[85vh] flex-col gap-0 p-0 sm:max-w-2xl">
      <DialogHeader class="px-6 pt-6 pb-4">
        <DialogTitle>{{ t('View settings') }}</DialogTitle>
        <DialogDescription>{{ t('Choose which columns to show, how to group and sort the records') }}</DialogDescription>
      </DialogHeader>

      <Tabs v-model="activeTab" class="min-h-0 flex-1 gap-0">
        <div class="px-6">
          <TabsList class="w-full">
            <TabsTrigger value="columns" class="flex-1 gap-1.5">
              <Columns3 class="size-4" />
              {{ t('Columns') }}
              <span class="tabular-nums text-muted-foreground">{{ columns.visibleColumns.value.length }}</span>
            </TabsTrigger>
            <TabsTrigger v-if="groupableFields.length" value="group" class="flex-1 gap-1.5">
              <Rows3 class="size-4" />
              {{ t('Grouping') }}
              <span v-if="groupBy" class="size-1.5 rounded-full bg-primary" />
            </TabsTrigger>
            <TabsTrigger value="sort" class="flex-1 gap-1.5">
              <ArrowUpDown class="size-4" />
              {{ t('Sorting') }}
              <span v-if="sortKey" class="size-1.5 rounded-full bg-primary" />
            </TabsTrigger>
          </TabsList>
        </div>

        <!-- Columns -->
        <TabsContent value="columns" class="px-6 py-4">
          <div class="grid gap-4 sm:grid-cols-2">
            <!-- Shown -->
            <div class="flex min-w-0 flex-col rounded-lg border">
              <div class="flex h-11 items-center justify-between border-b px-3">
                <span class="font-medium">{{ t('Shown') }}</span>
                <span class="tabular-nums text-muted-foreground">
                  {{ columns.visibleColumns.value.length }}/{{ columns.allAvailableColumns.value.length }}
                </span>
              </div>
              <div class="h-72 overflow-y-auto p-1">
                <VueDraggable
                  :model-value="columns.visibleColumns.value"
                  handle=".drag-handle"
                  ghost-class="opacity-40"
                  :animation="150"
                  class="space-y-0.5"
                  @end="onColReorder"
                >
                  <div v-for="col in columns.visibleColumns.value" :key="col.key" :class="rowClass">
                    <GripVertical class="drag-handle size-4 shrink-0 cursor-grab text-muted-foreground active:cursor-grabbing" />
                    <span class="flex-1 truncate">{{ col.label }}</span>
                    <Button
                      v-if="canHide"
                      variant="ghost"
                      size="icon"
                      class="size-6 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                      :aria-label="t('Hide')"
                      @click="columns.toggleCol(col.key)"
                    >
                      <X class="size-3.5" />
                    </Button>
                  </div>
                </VueDraggable>
              </div>
            </div>

            <!-- Available -->
            <div class="flex min-w-0 flex-col rounded-lg border">
              <div class="flex h-11 items-center gap-2 border-b px-2">
                <div class="relative flex-1">
                  <Search class="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input v-model="colSearch" class="h-8 border-0 pl-8 shadow-none focus-visible:ring-0" :placeholder="t('Search field...')" />
                </div>
                <Button
                  v-if="hiddenColumns.length"
                  variant="ghost"
                  size="sm"
                  class="h-7 shrink-0 text-muted-foreground"
                  @click="showAllCols"
                >
                  {{ t('Show all') }}
                </Button>
              </div>
              <div class="h-72 overflow-y-auto p-1">
                <div
                  v-for="col in filteredHiddenColumns"
                  :key="col.key"
                  :class="[rowClass, 'cursor-pointer']"
                  @click="columns.toggleCol(col.key)"
                >
                  <Plus class="size-4 shrink-0 text-muted-foreground" />
                  <span class="flex-1 truncate">{{ col.label }}</span>
                </div>
                <div v-if="!filteredHiddenColumns.length" class="px-2 py-8 text-center text-muted-foreground">
                  {{ hiddenColumns.length ? t('Nothing found') : t('All columns are shown') }}
                </div>
              </div>
            </div>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">{{ t('Drag to change the order of columns') }}</p>
        </TabsContent>

        <!-- Group by -->
        <TabsContent v-if="groupableFields.length" value="group" class="px-6 py-4">
          <div class="rounded-lg border">
            <div v-if="groupableFields.length > 8" class="border-b p-1">
              <div class="relative">
                <Search class="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input v-model="groupSearch" class="h-8 border-0 pl-8 shadow-none focus-visible:ring-0" :placeholder="t('Search field...')" />
              </div>
            </div>
            <div class="max-h-80 overflow-y-auto p-1">
              <div :class="[rowClass, 'cursor-pointer']" @click="emit('update:groupBy', null)">
                <Check class="size-4 shrink-0" :class="{ invisible: groupBy }" />
                <span class="flex-1 text-muted-foreground">{{ t('No grouping') }}</span>
              </div>
              <div
                v-for="f in filteredGroupFields"
                :key="f.fieldname"
                :class="[rowClass, 'cursor-pointer']"
                @click="emit('update:groupBy', f.fieldname)"
              >
                <Check class="size-4 shrink-0" :class="{ invisible: groupBy !== f.fieldname }" />
                <span class="flex-1 truncate" :class="{ 'font-medium': groupBy === f.fieldname }">{{ f.label }}</span>
              </div>
              <div v-if="!filteredGroupFields.length" class="px-2 py-6 text-center text-muted-foreground">{{ t('Nothing found') }}</div>
            </div>
          </div>
        </TabsContent>

        <!-- Sort -->
        <TabsContent value="sort" class="space-y-3 px-6 py-4">
          <div class="flex items-center justify-between gap-3">
            <span class="text-muted-foreground">{{ t('Sort order') }}</span>
            <div class="inline-flex rounded-md border p-0.5" :class="{ 'pointer-events-none opacity-50': !effectiveSortKey }">
              <Button
                variant="ghost"
                size="sm"
                class="h-7 gap-1.5"
                :class="effectiveSortKey && effectiveSortOrder === 'asc' && 'bg-accent text-accent-foreground'"
                @click="setSortOrder('asc')"
              >
                <ArrowUp class="size-3.5" />{{ t('Ascending') }}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                class="h-7 gap-1.5"
                :class="effectiveSortKey && effectiveSortOrder === 'desc' && 'bg-accent text-accent-foreground'"
                @click="setSortOrder('desc')"
              >
                <ArrowDown class="size-3.5" />{{ t('Descending') }}
              </Button>
            </div>
          </div>
          <div class="rounded-lg border">
            <div class="border-b p-1">
              <div class="relative">
                <Search class="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input v-model="sortSearch" class="h-8 border-0 pl-8 shadow-none focus-visible:ring-0" :placeholder="t('Search field...')" />
              </div>
            </div>
            <div class="max-h-72 overflow-y-auto p-1">
              <div
                v-for="opt in filteredSortOptions"
                :key="opt.key"
                :class="[rowClass, 'cursor-pointer']"
                @click="emit('sort', opt.key)"
              >
                <Check class="size-4 shrink-0" :class="{ invisible: effectiveSortKey !== opt.key }" />
                <span class="flex-1 truncate" :class="{ 'font-medium': effectiveSortKey === opt.key }">{{ opt.label }}</span>
                <span
                  v-if="opt.key === defaultSortKey"
                  class="shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
                >{{ t('Default') }}</span>
                <component
                  :is="effectiveSortOrder === 'asc' ? ArrowUp : ArrowDown"
                  v-if="effectiveSortKey === opt.key"
                  class="size-3.5 shrink-0"
                />
              </div>
              <div v-if="!filteredSortOptions.length" class="px-2 py-6 text-center text-muted-foreground">{{ t('Nothing found') }}</div>
            </div>
          </div>
        </TabsContent>
      </Tabs>

      <DialogFooter class="border-t px-6 py-4 sm:justify-between">
        <Button variant="ghost" :disabled="!isCustomized" class="gap-1.5" @click="resetAll">
          <RotateCcw class="size-4" />
          {{ t('Reset to default') }}
        </Button>
        <DialogClose as-child>
          <Button>{{ t('Done') }}</Button>
        </DialogClose>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</div>
</template>
