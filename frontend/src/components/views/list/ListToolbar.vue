<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Search,
  Columns3,
  X,
  LayoutList,
  LayoutGrid,
  CalendarDays,
  GitBranch,
  Rows3,
  Check,
  Image as ImageIcon,
  Map as MapIcon,
} from '@lucide/vue'
import draggable from 'vuedraggable'
import type { ActiveFilter, DocField, DocType, FastFilter } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import FilterBar from '@/components/views/FilterBar.vue'
import FastFilterBar from '@/components/views/FastFilterBar.vue'

type ViewMode = 'list' | 'kanban' | 'calendar' | 'tree' | 'gallery' | 'map'

interface ListColumnsState {
  allAvailableColumns: { value: ListColumn[] }
  visibleColumns: { value: ListColumn[] }
  isCustomized: { value: boolean }
  isVisible: (key: string) => boolean
  toggleCol: (key: string) => void
  reorderCols: (oldIndex: number, newIndex: number) => void
}

const props = defineProps<{
  dt: DocType | null
  doctype: string
  viewMode: ViewMode
  inlineSearch: string
  activeFilters: ActiveFilter[]
  fastFilterDefs: FastFilter[]
  fastFilterValues: Record<string, string>
  columns: ListColumnsState
  groupableFields: DocField[]
  groupBy: string | null
  groupByField: DocField | null
  kanbanColumnField: DocField | null
  treeParentField: DocField | null
  calendarDateField: DocField | null
  geoField: DocField | null
}>()

const emit = defineEmits<{
  (e: 'update:viewMode', val: ViewMode): void
  (e: 'update:inlineSearch', val: string): void
  (e: 'update:activeFilters', val: ActiveFilter[]): void
  (e: 'update:fastFilterValues', val: Record<string, string>): void
  (e: 'update:groupBy', val: string | null): void
  (e: 'reset'): void
}>()

const { t } = useI18n()

const localSearch = ref(props.inlineSearch)
watch(() => props.inlineSearch, (v) => { localSearch.value = v })
watch(localSearch, (v) => { emit('update:inlineSearch', v) })

function onFiltersChange(f: ActiveFilter[]) {
  emit('update:activeFilters', f)
}

function setGroupBy(field: string | null) {
  emit('update:groupBy', field)
}

function onColReorder(e: { oldIndex: number; newIndex: number }) {
  props.columns.reorderCols(e.oldIndex, e.newIndex)
}

// PrimeVue Popover refs
const opColumns = ref()
const opGrouping = ref()

const toggleColumns = (event: Event) => {
    opColumns.value.toggle(event)
}

const toggleGrouping = (event: Event) => {
    opGrouping.value.toggle(event)
}
</script>

<template>
  <div class="flex flex-col gap-0 bg-muted/30 rounded-xl ring-1 ring-border/40 mb-2">
    <!-- Main row: search + filters + view switcher -->
    <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-1.5">
      <!-- Left: search + filters -->
      <div class="flex flex-1 items-center gap-2">
        <div class="relative flex-1 max-w-[320px] group">
          <Search
            class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/60 transition-colors group-focus-within:text-primary" />
          <input v-model="localSearch"
            class="flex h-9 w-full rounded-lg border border-border/60 bg-background px-3 py-1 pl-9 text-sm text-foreground shadow-sm transition-all placeholder:text-muted-foreground/70 focus-visible:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/30"
            :placeholder="t('Search...')" />
        </div>
        <FastFilterBar
          v-if="dt && fastFilterDefs.length && ['list', 'tree'].includes(viewMode)"
          :defs="fastFilterDefs"
          :dt="dt"
          :scope="viewMode === 'tree' ? 'tree' : 'list'"
          :model-value="fastFilterValues"
          variant="quick"
          class="!px-0 !py-0"
          @update:model-value="emit('update:fastFilterValues', $event)"
        />
        <FilterBar v-if="dt" :fields="dt.fields" :doctype="doctype" :initial-filters="activeFilters" @change="onFiltersChange" class="!mb-0" />
        <Button v-if="inlineSearch || activeFilters.length" text size="small"
        class="h-8 px-2 text-muted-foreground hover:text-foreground hover:bg-muted/50" @click="emit('reset')">
        <X class="size-4 mr-1" />
        {{ t('Reset') }}
      </Button>
    </div>

    <!-- Right: columns + grouping + view switcher -->
    <div class="flex items-center gap-2 px-1">
      <div v-if="viewMode === 'list'" class="flex items-center gap-2 pr-1 border-r border-border/60 mr-1">
        <!-- Columns Popover -->
        <Button text size="small" class="h-9 px-2.5 gap-2 font-medium transition-all"
          :class="columns.isCustomized.value ? 'text-primary bg-primary/5' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
          @click="toggleColumns">
          <Columns3 class="size-4" />
          <span class="hidden lg:inline">Стовпці</span>
          <Badge v-if="columns.isCustomized.value" severity="secondary" class="bg-primary/20 text-primary hover:bg-primary/20 size-5 p-0 flex items-center justify-center text-[10px]">
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
                @end="onColReorder"
                class="space-y-0.5"
              >
                <template #item="{ element: col }">
                  <div class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group transition-colors"
                    @click="columns.toggleCol(col.key)">
                    <span class="drag-handle cursor-grab text-muted-foreground/30 hover:text-muted-foreground select-none">⠿</span>
                    <div class="size-4 flex items-center justify-center">
                       <Check class="size-3.5 text-primary" />
                    </div>
                    <span class="flex-1 truncate text-sm font-medium">{{ col.label }}</span>
                  </div>
                </template>
              </draggable>
              
              <div v-for="col in columns.allAvailableColumns.value.filter((c) => !columns.isVisible(c.key))"
                :key="col.key"
                class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group transition-colors"
                @click="columns.toggleCol(col.key)">
                <span class="size-4" />
                <div class="size-4 flex items-center justify-center opacity-0 group-hover:opacity-30">
                   <Check class="size-3.5" />
                </div>
                <span class="flex-1 truncate text-sm text-muted-foreground">{{ col.label }}</span>
              </div>
            </div>
          </div>
        </Popover>

        <!-- Group by Popover -->
        <Button v-if="groupableFields.length" text size="small" class="h-9 px-2.5 gap-2 font-medium transition-all"
          :class="groupBy ? 'text-primary bg-primary/5' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
          @click="toggleGrouping">
          <Rows3 class="size-4" />
          <span class="hidden lg:inline">{{ groupBy ? groupByField?.label : 'Групування' }}</span>
        </Button>

        <Popover ref="opGrouping">
          <div class="w-56 p-1">
            <div class="px-2 py-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground/80">Групувати за</div>
            <div class="h-px bg-border/40 my-1" />
            
            <div class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group transition-colors"
              @click="setGroupBy(null); opGrouping.hide()">
              <div class="size-4 flex items-center justify-center">
                <Check class="size-3.5 text-primary" :class="groupBy === null ? 'opacity-100' : 'opacity-0'" />
              </div>
              <span class="text-sm font-medium">Без групування</span>
            </div>
            
            <div class="h-px bg-border/40 my-1" />
            
            <div v-for="f in groupableFields" :key="f.fieldname" 
              class="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group transition-colors"
              @click="setGroupBy(f.fieldname); opGrouping.hide()">
              <div class="size-4 flex items-center justify-center">
                <Check class="size-3.5 text-primary" :class="groupBy === f.fieldname ? 'opacity-100' : 'opacity-0'" />
              </div>
              <span class="text-sm font-medium">{{ f.label }}</span>
            </div>
          </div>
        </Popover>
      </div>

      <!-- View mode switcher -->
      <div class="flex items-center bg-background/50 rounded-lg p-1 shadow-inner ring-1 ring-border/40">
        <button type="button" class="size-8 flex items-center justify-center rounded-md transition-all active:scale-90"
          :class="viewMode === 'list' ? 'bg-background shadow-sm text-primary ring-1 ring-border/60' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
          title="Список" @click="emit('update:viewMode', 'list')">
          <LayoutList class="size-4" />
        </button>
        <button v-if="kanbanColumnField" type="button"
          class="size-8 flex items-center justify-center rounded-md transition-all active:scale-90 ml-1"
          :class="viewMode === 'kanban' ? 'bg-background shadow-sm text-primary ring-1 ring-border/60' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
          title="Канбан" @click="emit('update:viewMode', 'kanban')">
          <LayoutGrid class="size-4" />
        </button>
        <button v-if="calendarDateField" type="button"
          class="size-8 flex items-center justify-center rounded-md transition-all active:scale-90 ml-1"
          :class="viewMode === 'calendar' ? 'bg-background shadow-sm text-primary ring-1 ring-border/60' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
          title="Календар" @click="emit('update:viewMode', 'calendar')">
          <CalendarDays class="size-4" />
        </button>
        <button v-if="treeParentField" type="button"
          class="size-8 flex items-center justify-center rounded-md transition-all active:scale-90 ml-1"
          :class="viewMode === 'tree' ? 'bg-background shadow-sm text-primary ring-1 ring-border/60' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
          title="Дерево" @click="emit('update:viewMode', 'tree')">
          <GitBranch class="size-4" />
        </button>
        <button type="button"
          class="size-8 flex items-center justify-center rounded-md transition-all active:scale-90 ml-1"
          :class="viewMode === 'gallery' ? 'bg-background shadow-sm text-primary ring-1 ring-border/60' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
          title="Галерея" @click="emit('update:viewMode', 'gallery')">
          <ImageIcon class="size-4" />
        </button>
        <button v-if="geoField" type="button"
          class="size-8 flex items-center justify-center rounded-md transition-all active:scale-90 ml-1"
          :class="viewMode === 'map' ? 'bg-background shadow-sm text-primary ring-1 ring-border/60' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
          title="Карта" @click="emit('update:viewMode', 'map')">
          <MapIcon class="size-4" />
        </button>
      </div>
    </div>
    </div>

    <!-- Fast filter bar (shown below main row when defs exist for current view) -->
    <FastFilterBar
      v-if="dt && fastFilterDefs.length && !['list', 'tree'].includes(viewMode)"
      :defs="fastFilterDefs"
      :dt="dt"
      :scope="['tree'].includes(viewMode) ? 'tree' : 'list'"
      :model-value="fastFilterValues"
      variant="default"
      class="border-t border-border/30 px-2"
      @update:model-value="emit('update:fastFilterValues', $event)"
    />
  </div>
</template>
