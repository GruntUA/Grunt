<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Filter, X, Bookmark, Plus, Users, Package } from '@lucide/vue'
import type { DocField, ActiveFilter } from '@/types'
import { getFilterConfig } from '@/core/filterRegistry'
import { isFilterableType } from '@/core/fieldRegistry'
import { MULTI_VALUE_OPS, NO_VALUE_OPS, opLabel } from '@/core/filterOps'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ButtonGroup } from '@/components/ui/button-group'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import type { ListFilterReset } from '@/core/composables/useListFilterReset'
import { savedFiltersApi, type FilterSharing, type SavedFilter } from '@/core/api/savedFilters'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/core/composables/useToast'
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

// Saved filters - on the server, own or shared with roles / everyone
// (grunt/api/v1/saved_filters.py). Only the owner deletes one.
const auth = useAuthStore()
const toast = useToast()
const savedPresets = ref<SavedFilter[]>([])
const showSaveName = ref(false)
const presetNameInput = ref('')
const presetSharing = ref<FilterSharing>('Nobody')
const presetRoles = ref<string[]>([])
// Share with one's own roles - no role directory to pick from.
const myRoles = computed(() => (auth.user?.roles ?? []).filter((r) => r !== 'All' && r !== 'Guest'))

async function loadPresets() {
  if (!props.doctype) return
  try {
    savedPresets.value = await savedFiltersApi.list(props.doctype)
    await migrateLocalPresets()
  } catch {
    savedPresets.value = []
  }
}

// Presets from before they lived on the server (localStorage) - sent up once as
// the user's own, then the local copy goes.
async function migrateLocalPresets() {
  const key = `grunt_filter_presets_${props.doctype}`
  let local: { name: string; filters: ActiveFilter[] }[] = []
  try {
    local = JSON.parse(localStorage.getItem(key) ?? '[]')
  } catch { /* unreadable - drop it */ }
  if (!Array.isArray(local) || !local.length) return
  const have = new Set(savedPresets.value.filter((p) => p.mine).map((p) => p.title))
  for (const p of local) {
    if (p?.name && p.filters?.length && !have.has(p.name)) {
      savedPresets.value.push(await savedFiltersApi.save(props.doctype!, p.name, p.filters))
    }
  }
  try { localStorage.removeItem(key) } catch { /* ignore */ }
}

watch(() => props.doctype, () => { void loadPresets() }, { immediate: true })

async function savePreset() {
  const name = presetNameInput.value.trim()
  const filters = buildFiltersFromDraft()
  if (!name || !filters.length || !props.doctype) return
  if (presetSharing.value === 'Roles' && !presetRoles.value.length) return
  try {
    const saved = await savedFiltersApi.save(
      props.doctype, name, filters, presetSharing.value, presetSharing.value === 'Roles' ? presetRoles.value : [],
    )
    savedPresets.value = [...savedPresets.value.filter((p) => !(p.mine && p.title === name)), saved]
      .sort((a, b) => a.title.localeCompare(b.title))
  } catch {
    toast.error(t('Could not save the filter'))
    return
  }
  showSaveName.value = false
  presetNameInput.value = ''
  presetSharing.value = 'Nobody'
  presetRoles.value = []
  activeFilters.value = filters
  emitChange()
}

function applyPreset(preset: SavedFilter) {
  draftRows.value = preset.filters.map(f => ({ fieldname: f.fieldname, op: f.op, value: f.value, displayValue: f.displayValue ?? '' }))
}

async function deletePreset(preset: SavedFilter) {
  try {
    await savedFiltersApi.remove(preset.name)
    savedPresets.value = savedPresets.value.filter((p) => p.name !== preset.name)
  } catch {
    toast.error(t('Could not delete the filter'))
  }
}

function toggleRole(role: string, on: boolean) {
  presetRoles.value = on ? [...presetRoles.value, role] : presetRoles.value.filter((r) => r !== role)
}

// Field list
// A field already filtered on (e.g. a dashboard drill-down URL) stays pickable
// even without `in_filter`, so its row renders and can be edited.
const filterableFields = computed(() => {
  const used = new Set([...activeFilters.value, ...draftRows.value].map(f => f.fieldname))
  return props.fields.filter(f =>
    (props.allFields || f.in_filter || used.has(f.fieldname))
    && isFilterableType(f.fieldtype),
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
        class="w-[min(560px,calc(100vw-2rem))]" align="start"
        @pointer-down-outside="keepOpenForLinkDropdown"
        @focus-outside="keepOpenForLinkDropdown"
      >
        <div class="-m-1 flex max-h-80 flex-col gap-2 overflow-y-auto p-1">
          <div v-for="(row, i) in draftRows" :key="i" class="flex flex-wrap sm:flex-nowrap items-center gap-2">
            <Select :model-value="row.fieldname" @update:model-value="(v: unknown) => onFieldChange(row, String(v))">
              <SelectTrigger class="w-[calc(50%-1.75rem)] sm:w-36 shrink-0">
                <SelectValue :placeholder="t('Field')" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="f in filterableFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>

            <Select :model-value="row.op" @update:model-value="(v: unknown) => onOpChange(row, String(v))">
              <SelectTrigger class="w-[calc(50%-1.75rem)] sm:w-36 shrink-0">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  v-for="op in getFilterConfig(fieldFor(row.fieldname)?.fieldtype ?? '_default').operators"
                  :key="op" :value="op"
                >{{ opLabel(op, t) }}</SelectItem>
              </SelectContent>
            </Select>

            <div class="order-last basis-full sm:order-none sm:basis-auto flex-1 min-w-0">
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
              variant="outline" class="cursor-pointer hover:bg-accent" :class="preset.mine && !preset.standard && 'pr-1'"
              :title="preset.standard ? t('Filter from the app') : preset.shared_with !== 'Nobody' ? t('Shared filter') : undefined"
              @click="applyPreset(preset)"
            >
              <Package v-if="preset.standard" class="text-muted-foreground" />
              <Users v-else-if="preset.shared_with !== 'Nobody'" class="text-muted-foreground" />
              {{ preset.title }}
              <button v-if="preset.mine && !preset.standard" type="button" class="hover:text-destructive" :aria-label="t('Remove')" @click.stop="deletePreset(preset)">
                <X />
              </button>
            </Badge>
          </div>
        </template>

        <Separator class="my-3" />

        <div class="flex flex-wrap items-center justify-between gap-2">
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
                <Select v-model="presetSharing">
                  <SelectTrigger class="w-36" :aria-label="t('Shared with')"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Nobody">{{ t('Only me') }}</SelectItem>
                    <SelectItem v-if="myRoles.length" value="Roles">{{ t('My roles…') }}</SelectItem>
                    <SelectItem value="Everyone">{{ t('Everyone') }}</SelectItem>
                  </SelectContent>
                </Select>
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
          <Button class="ml-auto" @click="applyDraft">
            {{ t('Apply Filters') }}
          </Button>
        </div>
        <div v-if="showSaveName && presetSharing === 'Roles'" class="mt-2 flex flex-wrap gap-x-4 gap-y-2">
          <label v-for="role in myRoles" :key="role" class="flex items-center gap-2 text-sm">
            <Checkbox :model-value="presetRoles.includes(role)" @update:model-value="toggleRole(role, !!$event)" />
            {{ role }}
          </label>
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>
