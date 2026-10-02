<script setup lang="ts">
import { ref, watch, computed, inject, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@lucide/vue'
import type { ActiveFilter, DocType, QuickFilter } from '@/types'
import FilterBar from '@/components/views/FilterBar.vue'
import QuickFilterBar from '@/components/views/QuickFilterBar.vue'
import { getViewDef, type ToolbarContext } from '@/core/viewRegistry'
import { Input } from '@/components/ui/input'
import { LIST_FILTER_RESET } from '@/core/composables/useListFilterReset'

const props = defineProps<{
  dt: DocType | null
  doctype: string
  viewMode: string
  inlineSearch: string
  activeFilters: ActiveFilter[]
  quickFilterDefs: QuickFilter[]
  quickFilterValues: Record<string, string>
  /** Opaque view-specific data forwarded to the active view's toolbarControls. */
  viewExtras?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:viewMode': [val: string]
  'update:inlineSearch': [val: string]
  'update:activeFilters': [val: ActiveFilter[]]
  'update:quickFilterValues': [val: Record<string, string>]
  'update:groupBy': [val: string | null]
  sort: [key: string]
}>()

const { t } = useI18n()

const localSearch = ref(props.inlineSearch)
watch(() => props.inlineSearch, (v) => { localSearch.value = v })
watch(localSearch, (v) => { emit('update:inlineSearch', v) })

// Reset of search + filters + quick filters, provided by the list page —
// wired into the ✕ of the Filter split button.
const filterReset = inject(LIST_FILTER_RESET, null)

// ── Active view's toolbar controls ───────────────────────────────────────────

const viewDef = computed(() => getViewDef(props.viewMode))

const toolbarControlsComponent = computed(() => {
  const loader = viewDef.value?.toolbarControls
  return loader ? defineAsyncComponent(loader) : null
})

const toolbarCtx = computed((): ToolbarContext => ({
  dt: props.dt,
  doctype: props.doctype,
  viewMode: props.viewMode,
  inlineSearch: props.inlineSearch,
  activeFilters: props.activeFilters,
  quickFilterDefs: props.quickFilterDefs,
  quickFilterValues: props.quickFilterValues,
  extras: props.viewExtras ?? {},
  emit: {
    updateViewMode: (val) => emit('update:viewMode', val),
    updateInlineSearch: (val) => emit('update:inlineSearch', val),
    updateActiveFilters: (val) => emit('update:activeFilters', val),
    updateQuickFilterValues: (val) => emit('update:quickFilterValues', val),
    updateGroupBy: (val) => emit('update:groupBy', val),
    sort: (key) => emit('sort', key),
  },
}))

const toolbarControlsProps = computed(() =>
  viewDef.value?.mountToolbarProps?.(toolbarCtx.value) ?? {}
)
const toolbarControlsEvents = computed(() =>
  viewDef.value?.mountToolbarEvents?.(toolbarCtx.value) ?? {}
)
</script>

<template>
  <div class="flex flex-col gap-0">
    <!-- Main row: search + filters + view-controls + view switcher -->
    <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">

      <!-- Left: search + fast filters + active filters + reset -->
      <div class="flex flex-1 flex-wrap items-center gap-2">
        <div class="relative w-full max-w-[260px]">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input v-model="localSearch" class="h-8 pl-9" :placeholder="t('Search...')" />
        </div>
        <!-- Quick filters render inline for every view (labels carried by placeholders). -->
        <QuickFilterBar
          v-if="dt && quickFilterDefs.length"
          :defs="quickFilterDefs"
          :dt="dt"
          :scope="viewMode === 'tree' ? 'tree' : 'list'"
          :model-value="quickFilterValues"
          variant="quick"
          class="!px-0 !py-0"
          @update:model-value="emit('update:quickFilterValues', $event)"
        />
        <FilterBar
          v-if="dt"
          :fields="dt.fields"
          :doctype="doctype"
          :initial-filters="activeFilters"
          :reset="filterReset"
          class="!mb-0"
          @change="emit('update:activeFilters', $event)"
        />
      </div>

      <!-- Right: active view's toolbar controls (columns, grouping, sort, etc.) -->
      <!-- View mode switcher itself lives in ListHeader.vue ("View ▾" dropdown) -->
      <div v-if="toolbarControlsComponent" class="flex items-center gap-2">
        <component
          :is="toolbarControlsComponent"
          v-bind="{ ...toolbarControlsProps, ...toolbarControlsEvents }"
        />
      </div>
    </div>
  </div>
</template>
