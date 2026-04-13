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
} from 'lucide-vue-next'
import draggable from 'vuedraggable'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import FilterBar from '@/components/views/FilterBar.vue'

const props = defineProps<{
  dt: any
  doctype: string
  viewMode: string
  inlineSearch: string
  activeFilters: Record<string, string>
  columns: any
  groupableFields: any[]
  groupBy: string | null
  groupByField: any | null
  kanbanColumnField: any
  treeParentField: any
  calendarDateField: any
  geoField: any
}>()

const emit = defineEmits<{
  (e: 'update:viewMode', val: any): void
  (e: 'update:inlineSearch', val: string): void
  (e: 'update:activeFilters', val: Record<string, string>): void
  (e: 'update:groupBy', val: string | null): void
  (e: 'reset'): void
}>()

const { t } = useI18n()
const showColMenu = ref(false)

const localSearch = ref(props.inlineSearch)
watch(() => props.inlineSearch, (v) => { localSearch.value = v })
watch(localSearch, (v) => { emit('update:inlineSearch', v) })

function onFiltersChange(f: Record<string, string>) {
  emit('update:activeFilters', f)
}

function setGroupBy(field: string | null) {
  emit('update:groupBy', field)
}

function onColReorder(e: { oldIndex: number; newIndex: number }) {
  props.columns.reorderCols(e.oldIndex, e.newIndex)
}
</script>

<template>
  <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-1.5 bg-muted/30 rounded-xl ring-1 ring-border/40 mb-2">
    <!-- Left: search + filters -->
    <div class="flex flex-1 items-center gap-2">
      <div class="relative flex-1 max-w-[320px] group">
        <Search
          class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/60 transition-colors group-focus-within:text-primary" />
        <input v-model="localSearch"
          class="flex h-9 w-full rounded-lg border-transparent bg-background/60 px-3 py-1 pl-9 text-sm text-foreground transition-all placeholder:text-muted-foreground/60 focus-visible:outline-none focus:bg-background focus:ring-1 focus:ring-primary/30"
          :placeholder="t('Search...')" />
      </div>
      <FilterBar v-if="dt" :fields="dt.fields" :doctype="doctype" @change="onFiltersChange" class="!mb-0" />
      <Button v-if="inlineSearch || Object.keys(activeFilters).length" variant="ghost" size="sm"
        class="h-8 px-2 text-muted-foreground hover:text-foreground" @click="emit('reset')">
        <X class="size-4 mr-1" />
        {{ t('Reset') }}
      </Button>
    </div>

    <!-- Right: columns + grouping + view switcher -->
    <div class="flex items-center gap-2 px-1">
      <div v-if="viewMode === 'list'" class="flex items-center gap-2 pr-1 border-r border-border/60 mr-1">
        <!-- Columns dropdown -->
        <DropdownMenu v-model:open="showColMenu">
          <DropdownMenuTrigger as-child>
            <Button variant="ghost" size="sm" class="h-9 px-2.5 gap-2 font-medium" :class="columns.isCustomized.value
              ? 'text-primary bg-primary/5'
              : 'text-muted-foreground hover:text-foreground'">
              <Columns3 class="size-4" />
              <span class="hidden lg:inline">Стовпці</span>
              <Badge v-if="columns.isCustomized.value" variant="secondary" class="bg-primary/20 text-primary hover:bg-primary/20 size-5 p-0 flex items-center justify-center text-[10px]">
                {{ columns.visibleColumns.value.length }}
              </Badge>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-56 p-1.5">
            <DropdownMenuLabel class="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-muted-foreground">
              <span>Стовпці</span>
              <span class="tabular-nums opacity-60">
                {{ columns.visibleColumns.value.length }}/{{ columns.allAvailableColumns.value.length }}
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <draggable
              :model-value="columns.visibleColumns.value"
              item-key="key"
              handle=".drag-handle"
              @end="onColReorder"
            >
              <template #item="{ element: col }">
                <DropdownMenuItem class="gap-2 focus:bg-primary/5" @select.prevent="columns.toggleCol(col.key)">
                  <span class="drag-handle cursor-grab text-muted-foreground/30 hover:text-muted-foreground select-none">⠿</span>
                  <div class="size-4 flex items-center justify-center">
                     <Check class="size-3.5 text-primary" />
                  </div>
                  <span class="flex-1 truncate">{{ col.label }}</span>
                </DropdownMenuItem>
              </template>
            </draggable>
            <DropdownMenuItem
              v-for="col in columns.allAvailableColumns.value.filter((c: any) => !columns.isVisible(c.key))"
              :key="col.key"
              class="gap-2 group"
              @select.prevent="columns.toggleCol(col.key)">
              <span class="size-4" />
              <div class="size-4 flex items-center justify-center opacity-0 group-hover:opacity-30">
                 <Check class="size-3.5" />
              </div>
              <span class="flex-1 truncate text-muted-foreground">{{ col.label }}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <!-- Group by dropdown -->
        <DropdownMenu v-if="groupableFields.length">
          <DropdownMenuTrigger as-child>
            <Button variant="ghost" size="sm" class="h-9 px-2.5 gap-2 font-medium"
              :class="groupBy ? 'text-primary bg-primary/5' : 'text-muted-foreground hover:text-foreground'">
              <Rows3 class="size-4" />
              <span class="hidden lg:inline">{{ groupBy ? groupByField?.label : 'Групування' }}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-56 p-1.5">
            <DropdownMenuLabel class="text-xs font-bold uppercase tracking-wider text-muted-foreground">Групувати за</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem class="gap-2" @click="setGroupBy(null)">
              <div class="size-4 flex items-center justify-center">
                <Check class="size-3.5" :class="groupBy === null ? 'opacity-100' : 'opacity-0'" />
              </div>
              <span>Без групування</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem v-for="f in groupableFields" :key="f.fieldname" class="gap-2"
              @click="setGroupBy(f.fieldname)">
              <div class="size-4 flex items-center justify-center">
                <Check class="size-3.5 text-primary" :class="groupBy === f.fieldname ? 'opacity-100' : 'opacity-0'" />
              </div>
              <span>{{ f.label }}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
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
</template>
