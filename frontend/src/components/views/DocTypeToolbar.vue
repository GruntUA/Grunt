<script setup lang="ts">
import { ref, watch, computed, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@lucide/vue'
import type { ActiveFilter, DocType, FastFilter } from '@/types'
import FilterBar from '@/components/views/FilterBar.vue'
import FastFilterBar from '@/components/views/FastFilterBar.vue'
import { getViewDef, type ToolbarContext } from '@/core/viewRegistry'
import { Input } from '@/components/ui/input'

const props = defineProps<{
  dt: DocType | null
  doctype: string
  viewMode: string
  inlineSearch: string
  activeFilters: ActiveFilter[]
  fastFilterDefs: FastFilter[]
  fastFilterValues: Record<string, string>
  /** Opaque view-specific data forwarded to the active view's toolbarControls. */
  viewExtras?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:viewMode': [val: string]
  'update:inlineSearch': [val: string]
  'update:activeFilters': [val: ActiveFilter[]]
  'update:fastFilterValues': [val: Record<string, string>]
  'update:groupBy': [val: string | null]
  sort: [key: string]
}>()

const { t } = useI18n()

const localSearch = ref(props.inlineSearch)
watch(() => props.inlineSearch, (v) => { localSearch.value = v })
watch(localSearch, (v) => { emit('update:inlineSearch', v) })

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
  fastFilterDefs: props.fastFilterDefs,
  fastFilterValues: props.fastFilterValues,
  extras: props.viewExtras ?? {},
  emit: {
    updateViewMode: (val) => emit('update:viewMode', val),
    updateInlineSearch: (val) => emit('update:inlineSearch', val),
    updateActiveFilters: (val) => emit('update:activeFilters', val),
    updateFastFilterValues: (val) => emit('update:fastFilterValues', val),
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
      <div class="flex flex-1 items-center gap-2">
        <div class="relative w-full max-w-[260px]">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input v-model="localSearch" class="h-8 pl-9" :placeholder="t('Search...')" />
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
        <FilterBar
          v-if="dt"
          :fields="dt.fields"
          :doctype="doctype"
          :initial-filters="activeFilters"
          class="!mb-0"
          @change="emit('update:activeFilters', $event)"
        />
      </div>

      <!-- Right: active view's toolbar controls (columns, grouping, sort, etc.) -->
      <!-- View mode switcher itself lives in ListHeader.vue (Frappe-style "View ▾" dropdown) -->
      <div v-if="toolbarControlsComponent" class="flex items-center gap-2">
        <component
          :is="toolbarControlsComponent"
          v-bind="{ ...toolbarControlsProps, ...toolbarControlsEvents }"
        />
      </div>
    </div>

    <!-- Fast filter bar (shown below main row for non-list/tree views) -->
    <FastFilterBar
      v-if="dt && fastFilterDefs.length && !['list', 'tree'].includes(viewMode)"
      :defs="fastFilterDefs"
      :dt="dt"
      :scope="['tree'].includes(viewMode) ? 'tree' : 'list'"
      :model-value="fastFilterValues"
      variant="default"
      class="border-t border-border/30 pt-2"
      @update:model-value="emit('update:fastFilterValues', $event)"
    />
  </div>
</template>
