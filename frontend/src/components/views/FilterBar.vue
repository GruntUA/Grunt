<script setup lang="ts">
import { N_ } from '@/plugins/i18n'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Filter, X, Bookmark, Plus } from '@lucide/vue'
import type { DocField, ActiveFilter } from '@/types'
import { getFilterConfig } from '@/core/filterRegistry'
import { MULTI_VALUE_OPS, NO_VALUE_OPS } from '@/core/api/docs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
import type { ListFilterReset } from '@/core/composables/useListFilterReset'
const props = defineProps<{
  fields: DocField[]
  doctype?: string
  initialFilters?: ActiveFilter[]
  /** Offer every data field, not just `in_filter` ones (dashboard widget config). */
  allFields?: boolean
  /** Widens the trigger's ✕ to reset search and quick filters too (list toolbar). */
  reset?: ListFilterReset | null
}>()

const emit = defineEmits<{ change: [filters: ActiveFilter[]] }>()

interface FilterPreset { name: string; filters: ActiveFilter[] }

interface DraftRow {
  fieldname: string
  op: string
  value: string
  displayValue: string
}

const { t } = useI18n()
const activeFilters = ref<ActiveFilter[]>(props.initialFilters ?? [])
// Filters can be cleared from outside too (list empty state -> «Скинути фільтри»).
watch(() => props.initialFilters, (v) => { activeFilters.value = v ?? [] })

// Filter popover
const isFilterOpen = ref(false)
const filterAnchorEl = ref<HTMLElement | null>(null)

// Saved presets
const presetKey = computed(() => props.doctype ? `grunt_filter_presets_${props.doctype}` : null)
const savedPresets = ref<FilterPreset[]>(loadPresets())
const showSaveName = ref(false)
const presetNameInput = ref('')

function loadPresets(): FilterPreset[] {
  if (!props.doctype) return []
  try {
    const raw = localStorage.getItem(`grunt_filter_presets_${props.doctype}`)
    return raw ? (JSON.parse(raw) as FilterPreset[]) : []
  } catch { return [] }
}

function persistPresets() {
  if (!presetKey.value) return
  localStorage.setItem(presetKey.value, JSON.stringify(savedPresets.value))
}

function savePreset() {
  const name = presetNameInput.value.trim()
  const filters = buildFiltersFromDraft()
  if (!name || !filters.length) return
  savedPresets.value = [...savedPresets.value.filter(p => p.name !== name), { name, filters }]
  persistPresets()
  showSaveName.value = false
  presetNameInput.value = ''
  activeFilters.value = filters
  emitChange()
}

function applyPreset(preset: FilterPreset) {
  draftRows.value = preset.filters.map(f => ({ fieldname: f.fieldname, op: f.op, value: f.value, displayValue: f.displayValue ?? '' }))
}

function deletePreset(name: string) {
  savedPresets.value = savedPresets.value.filter(p => p.name !== name)
  persistPresets()
}

// Field list
// A field already filtered on (e.g. a dashboard drill-down URL) stays pickable
// even without `in_filter`, so its row renders and can be edited.
const filterableFields = computed(() => {
  const used = new Set([...activeFilters.value, ...draftRows.value].map(f => f.fieldname))
  return props.fields.filter(f =>
    (props.allFields || f.in_filter || used.has(f.fieldname))
    && !['Section', 'Column', 'Tab', 'Table', 'HTML', 'Button'].includes(f.fieldtype),
  )
})

function fieldFor(fieldname: string): DocField | undefined {
  return props.fields.find(f => f.fieldname === fieldname)
}

// Draft rows (edited freely inside the popover, committed on Apply)
const draftRows = ref<DraftRow[]>([])

function makeEmptyRow(): DraftRow {
  const f = filterableFields.value[0]
  const row = { fieldname: '', op: '=', value: '', displayValue: '' }
  if (f) onFieldChange(row, f.fieldname)
  return row
}

watch(isFilterOpen, (open) => {
  if (!open) return
  draftRows.value = activeFilters.value.length
    ? activeFilters.value.map(f => ({ fieldname: f.fieldname, op: f.op, value: f.value, displayValue: f.displayValue ?? '' }))
    : [makeEmptyRow()]
})

function addRow() {
  draftRows.value.push(makeEmptyRow())
}

function removeRow(i: number) {
  draftRows.value.splice(i, 1)
}

function onFieldChange(row: DraftRow, fieldname: string) {
  const f = fieldFor(fieldname)
  row.fieldname = fieldname
  row.value = ''
  row.displayValue = ''
  onOpChange(row, f ? getFilterConfig(f.fieldtype).operators[0] : '=')
}

function onOpChange(row: DraftRow, op: string) {
  const wasNoValue = row.op in NO_VALUE_OPS
  // Leaving a list operator: keep just the first value.
  if (MULTI_VALUE_OPS.includes(row.op) && !MULTI_VALUE_OPS.includes(op)) {
    row.value = row.value.split(',')[0] ?? ''
    row.displayValue = ''
  }
  row.op = op
  if (op in NO_VALUE_OPS) {
    row.value = NO_VALUE_OPS[op]
    row.displayValue = ''
  } else if (wasNoValue) {
    row.value = ''
  }
}

function buildFiltersFromDraft(): ActiveFilter[] {
  return draftRows.value
    .filter(r => r.fieldname && r.value)
    .map((r) => {
      const f = fieldFor(r.fieldname)!
      return {
        fieldname: r.fieldname,
        label: f.label,
        fieldtype: f.fieldtype,
        op: r.op,
        value: r.value,
        displayValue: r.displayValue || undefined,
      }
    })
}

function applyDraft() {
  activeFilters.value = buildFiltersFromDraft()
  isFilterOpen.value = false
  emitChange()
}

function clearAll() {
  activeFilters.value = []
  isFilterOpen.value = false
  emitChange()
}

const canClear = computed(() => activeFilters.value.length > 0 || !!props.reset?.active.value)

function clearEverything() {
  if (!props.reset) return clearAll()
  isFilterOpen.value = false
  props.reset.clear()
}

function emitChange() {
  emit('change', activeFilters.value)
}

const OP_LABELS: Record<string, string> = {
  '=': N_('Equals'),
  '!=': N_('Not equals'),
  'like': N_('Contains'),
  'not like': N_('Does not contain'),
  'is not set': N_('Is empty'),
  'is set': N_('Is set'),
  '>': N_('Greater than'),
  '<': N_('Less than'),
  '>=': N_('Greater than or equal'),
  '<=': N_('Less than or equal'),
  'child_of': N_('Descendant of'),
  'in': N_('Is one of'),
  'not in': N_('Is none of'),
}

function opLabel(op: string): string {
  return OP_LABELS[op] ? t(OP_LABELS[op]) : op
}

function toggleFilter(event: Event) {
  if (isFilterOpen.value) { isFilterOpen.value = false; return }
  filterAnchorEl.value = event.currentTarget as HTMLElement
  isFilterOpen.value = true
}

/**
 * Link/MultiLink filter inputs teleport their result dropdown to <body>, outside
 * this popover's DOM subtree - without this, clicking a result reads as an
 * "outside" interaction and closes the whole filter popover before the click
 * can register.
 */
function keepOpenForLinkDropdown(e: CustomEvent<{ originalEvent?: Event }>) {
  const target = (e.detail?.originalEvent?.target ?? e.target) as HTMLElement | null
  if (target?.closest?.('[data-link-dropdown]')) e.preventDefault()
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <!-- Trigger -->
    <ButtonGroup>
      <Button variant="outline" @click="toggleFilter">
        <Filter />
        {{ t('Filter') }}
        <Badge v-if="activeFilters.length" variant="secondary" class="rounded-sm px-1 font-normal tabular-nums">
          {{ activeFilters.length }}
        </Badge>
      </Button>
      <Button v-if="canClear" variant="outline" size="icon" :title="t('Clear Filters')" @click="clearEverything">
        <X />
      </Button>
    </ButtonGroup>

    <Popover :open="isFilterOpen" @update:open="(v: boolean) => { isFilterOpen = v }">
      <PopoverAnchor :reference="filterAnchorEl ?? undefined" />
      <PopoverContent
        class="w-[560px]" align="start"
        @pointer-down-outside="keepOpenForLinkDropdown"
        @focus-outside="keepOpenForLinkDropdown"
      >
        <div class="-m-1 flex max-h-80 flex-col gap-2 overflow-y-auto p-1">
          <div v-for="(row, i) in draftRows" :key="i" class="flex items-center gap-2">
            <Select :model-value="row.fieldname" @update:model-value="(v: unknown) => onFieldChange(row, String(v))">
              <SelectTrigger class="w-36 shrink-0">
                <SelectValue :placeholder="t('Field')" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="f in filterableFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>

            <Select :model-value="row.op" @update:model-value="(v: unknown) => onOpChange(row, String(v))">
              <SelectTrigger class="w-36 shrink-0">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="op in getFilterConfig(fieldFor(row.fieldname)?.fieldtype ?? '_default').operators"
                  :key="op" :value="op"
                >{{ opLabel(op) }}</SelectItem>
              </SelectContent>
            </Select>

            <div class="flex-1 min-w-0">
              <component
                :is="getFilterConfig(fieldFor(row.fieldname)?.fieldtype ?? '_default').filterInput"
                v-if="fieldFor(row.fieldname) && !(row.op in NO_VALUE_OPS)"
                :field="fieldFor(row.fieldname)"
                :model-value="row.value"
                :display-value="row.displayValue"
                :op="row.op"
                @update:model-value="row.value = $event"
                @update:display-value="row.displayValue = $event"
                @submit="applyDraft"
              />
            </div>

            <Button variant="ghost" size="icon" class="shrink-0 text-muted-foreground hover:text-destructive" :aria-label="t('Remove')" @click="removeRow(i)">
              <X />
            </Button>
          </div>

          <p v-if="!filterableFields.length" class="text-sm text-muted-foreground">
            {{ t('No fields available') }}
          </p>
        </div>

        <Button
          v-if="filterableFields.length"
          variant="ghost" size="sm"
          class="mt-2 text-muted-foreground"
          @click="addRow"
        >
          <Plus />
          {{ t('Add a Filter') }}
        </Button>

        <!-- Saved presets -->
        <template v-if="doctype && savedPresets.length">
          <Separator class="my-2" />
          <p class="mb-2 text-sm text-muted-foreground">{{ t('Saved filters') }}</p>
          <div class="flex flex-wrap gap-1">
            <Badge
              v-for="preset in savedPresets" :key="preset.name"
              variant="outline" class="cursor-pointer pr-1 hover:bg-accent"
              @click="applyPreset(preset)"
            >
              {{ preset.name }}
              <button type="button" class="hover:text-destructive" :aria-label="t('Remove')" @click.stop="deletePreset(preset.name)">
                <X />
              </button>
            </Badge>
          </div>
        </template>

        <Separator class="my-3" />

        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-1">
            <Button variant="ghost" class="text-muted-foreground" @click="clearAll">
              {{ t('Clear Filters') }}
            </Button>
            <template v-if="doctype">
              <template v-if="showSaveName">
                <Input
                  v-model="presetNameInput"
                  class="w-36"
                  :placeholder="t('Preset name')"
                  autofocus
                  @keydown="(e: KeyboardEvent) => { if (e.key === 'Enter') savePreset(); else if (e.key === 'Escape') showSaveName = false }"
                />
                <Button @click="savePreset">OK</Button>
                <Button variant="ghost" size="icon" :aria-label="t('Cancel')" @click="showSaveName = false">
                  <X />
                </Button>
              </template>
              <Button v-else variant="ghost" size="icon" class="text-muted-foreground" :title="t('Save as preset')" :aria-label="t('Save as preset')" @click="showSaveName = true">
                <Bookmark />
              </Button>
            </template>
          </div>
          <Button @click="applyDraft">
            {{ t('Apply Filters') }}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>
