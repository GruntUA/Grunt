<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Filter, X, Bookmark, Plus } from '@lucide/vue'
import type { DocField, ActiveFilter } from '@/types'
import { getFilterConfig } from '@/core/filterRegistry'
import { NO_VALUE_OPS } from '@/core/api/docs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
const props = defineProps<{
  fields: DocField[]
  doctype?: string
  initialFilters?: ActiveFilter[]
  /** Offer every data field, not just `in_filter` ones (dashboard widget config). */
  allFields?: boolean
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

// Filter popover
const isFilterOpen = ref(false)
const filterAnchorEl = ref<HTMLElement | null>(null)

// ── Saved presets ───────────────────────────────────────────────────────────
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

// ── Field list ──────────────────────────────────────────────────────────────
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

// ── Draft rows (edited freely inside the popover, committed on Apply) ───────
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

function emitChange() {
  emit('change', activeFilters.value)
}

const OP_LABELS: Record<string, string> = {
  '=': 'Дорівнює',
  '!=': 'Не дорівнює',
  'like': 'Містить',
  'not like': 'Не містить',
  'is not set': 'Порожнє',
  'is set': 'Заповнене',
  '>': 'Більше',
  '<': 'Менше',
  '>=': 'Більше або дорівнює',
  '<=': 'Менше або дорівнює',
  'child_of': 'Підпорядковано',
}

function opLabel(op: string): string {
  return OP_LABELS[op] ?? op
}

function toggleFilter(event: Event) {
  if (isFilterOpen.value) { isFilterOpen.value = false; return }
  filterAnchorEl.value = event.currentTarget as HTMLElement
  isFilterOpen.value = true
}

/**
 * Link/MultiLink filter inputs teleport their result dropdown to <body>, outside
 * this popover's DOM subtree — without this, clicking a result reads as an
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
      <Button variant="outline" size="sm" class="h-7 text-xs gap-1.5" @click="toggleFilter">
        <Filter class="size-3" />
        {{ t('Filter') }}
        <Badge v-if="activeFilters.length" variant="secondary" class="h-4 px-1.5 text-[10px] tabular-nums">
          {{ activeFilters.length }}
        </Badge>
      </Button>
      <Button v-if="activeFilters.length" variant="outline" size="icon" class="h-7 w-7" :title="t('Clear Filters')" @click="clearAll">
        <X class="size-3.5" />
      </Button>
    </ButtonGroup>

    <Popover :open="isFilterOpen" @update:open="(v: boolean) => { isFilterOpen = v }">
      <PopoverAnchor :reference="filterAnchorEl ?? undefined" />
      <PopoverContent
        class="w-[440px] p-3" align="start"
        @pointer-down-outside="keepOpenForLinkDropdown"
        @focus-outside="keepOpenForLinkDropdown"
      >
        <div class="space-y-2 max-h-72 overflow-y-auto">
          <div v-for="(row, i) in draftRows" :key="i" class="flex items-center gap-1.5">
            <Select :model-value="row.fieldname" @update:model-value="(v: unknown) => onFieldChange(row, String(v))">
              <SelectTrigger size="sm" class="h-8 text-xs w-32 shrink-0">
                <SelectValue :placeholder="t('Field')" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="f in filterableFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>

            <Select :model-value="row.op" @update:model-value="(v: unknown) => onOpChange(row, String(v))">
              <SelectTrigger size="sm" class="h-8 text-xs w-32 shrink-0">
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

            <Button variant="ghost" size="icon" class="size-7 shrink-0 text-muted-foreground hover:text-destructive" @click="removeRow(i)">
              <X class="size-3.5" />
            </Button>
          </div>

          <p v-if="!filterableFields.length" class="text-muted-foreground italic px-1 py-1">
            {{ t('No fields available') }}
          </p>
        </div>

        <button
          v-if="filterableFields.length"
          type="button"
          class="flex items-center gap-1.5 text-muted-foreground hover:text-foreground mt-2 px-1 py-1"
          @click="addRow"
        >
          <Plus class="size-3.5" />
          {{ t('Add a Filter') }}
        </button>

        <!-- Saved presets -->
        <template v-if="doctype && savedPresets.length">
          <Separator class="my-2" />
          <p class="text-muted-foreground px-1 mb-1">{{ t('Saved filters') }}</p>
          <div class="flex flex-wrap gap-1">
            <Badge
              v-for="preset in savedPresets" :key="preset.name"
              variant="outline" class="cursor-pointer gap-1 pr-1 hover:bg-accent font-normal"
              @click="applyPreset(preset)"
            >
              {{ preset.name }}
              <button type="button" class="hover:text-destructive" @click.stop="deletePreset(preset.name)">
                <X class="size-3" />
              </button>
            </Badge>
          </div>
        </template>

        <Separator class="my-3" />

        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-1">
            <Button variant="ghost" size="sm" class="text-xs text-muted-foreground" @click="clearAll">
              {{ t('Clear Filters') }}
            </Button>
            <template v-if="doctype">
              <template v-if="showSaveName">
                <Input
                  v-model="presetNameInput"
                  class="h-7 text-xs w-28"
                  :placeholder="t('Preset name')"
                  autofocus
                  @keydown="(e: KeyboardEvent) => { if (e.key === 'Enter') savePreset(); else if (e.key === 'Escape') showSaveName = false }"
                />
                <Button size="sm" class="h-7 px-2.5 text-xs" @click="savePreset">OK</Button>
                <Button variant="ghost" size="icon" class="size-7" @click="showSaveName = false">
                  <X class="size-3.5" />
                </Button>
              </template>
              <Button v-else variant="ghost" size="icon" class="size-7 text-muted-foreground" :title="t('Save as preset')" @click="showSaveName = true">
                <Bookmark class="size-3.5" />
              </Button>
            </template>
          </div>
          <Button size="sm" class="text-xs" @click="applyDraft">
            {{ t('Apply Filters') }}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>
