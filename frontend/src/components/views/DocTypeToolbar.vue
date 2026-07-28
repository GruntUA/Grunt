<script setup lang="ts">
import { ref, watch, computed, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search, X } from '@lucide/vue'
import type { ActiveFilter, DocType, FastFilter } from '@/types'
import FilterBar from '@/components/views/FilterBar.vue'
import FastFilterBar from '@/components/views/FastFilterBar.vue'
import { getRegisteredViews, getViewDef, type ToolbarContext } from '@/core/viewRegistry'

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
  reset: []
}>()

const { t } = useI18n()

const localSearch = ref(props.inlineSearch)
watch(() => props.inlineSearch, (v) => { localSearch.value = v })
watch(localSearch, (v) => { emit('update:inlineSearch', v) })

// ── Available view buttons ────────────────────────────────────────────────────

const availableViews = computed(() =>
  getRegisteredViews().filter((def) => {
    if (!def.resolveField) return true
    if (!props.dt) return false
    return def.resolveField(props.dt) !== null
  })
)

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
    reset: () => emit('reset'),
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
  <div class="flex flex-col gap-0 bg-muted/30 rounded-lg ring-1 ring-border/40 mb-2">
    <!-- Main row: search + filters + view-controls + view switcher -->
    <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-1.5">

      <!-- Left: search + fast filters + active filters + reset -->
      <div class="flex flex-1 items-center gap-2">
        <div class="relative flex-1 max-w-[320px] group">
          <Search
            class="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/60 transition-colors group-focus-within:text-primary" />
          <input
            v-model="localSearch"
            class="flex h-9 w-full rounded-lg border border-border/60 bg-background px-3 py-1 pl-9 text-sm text-foreground shadow-sm transition-all placeholder:text-muted-foreground/70 focus-visible:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/30"
            :placeholder="t('Search...')"
          />
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
        <Button variant="ghost" v-if="inlineSearch || activeFilters.length" size="sm" class="h-8 px-2 text-muted-foreground hover:text-foreground hover:bg-muted/50" @click="emit('reset')">
          <X class="size-4 mr-1" />
          {{ t('Reset') }}
        </Button>
      </div>

      <!-- Right: view toolbar controls + view switcher -->
      <div class="flex items-center gap-2 px-1">

        <!-- Active view's toolbar controls (columns, grouping, sort, etc.) -->
        <div
          v-if="toolbarControlsComponent"
          class="flex items-center gap-2 pr-1 border-r border-border/60 mr-1"
        >
          <component
            :is="toolbarControlsComponent"
            v-bind="{ ...toolbarControlsProps, ...toolbarControlsEvents }"
          />
        </div>

        <!-- View mode switcher — driven by viewRegistry -->
        <div class="flex items-center bg-background/50 rounded-lg p-1 ring-1 ring-border/40">
          <button
            v-for="(def, i) in availableViews"
            :key="def.type"
            type="button"
            class="size-8 flex items-center justify-center rounded-md transition-colors"
            :class="[
              i > 0 ? 'ml-1' : '',
              viewMode === def.type
                ? 'bg-background shadow-sm text-primary ring-1 ring-border/60'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
            ]"
            :title="def.label"
            @click="emit('update:viewMode', def.type)"
          >
            <component :is="def.icon" class="size-4" />
          </button>
        </div>
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
      class="border-t border-border/30 px-2"
      @update:model-value="emit('update:fastFilterValues', $event)"
    />
  </div>
</template>
