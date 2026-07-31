<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField, ActiveFilter } from '@/types'
import { Filter, X, Bookmark, ChevronDown, ChevronLeft, Trash2, Pencil } from '@lucide/vue'
import { getFilterConfig } from '@/core/filterRegistry'

const props = defineProps<{
  fields: DocField[]
  doctype?: string
  initialFilters?: ActiveFilter[]
}>()

const emit = defineEmits<{ change: [filters: ActiveFilter[]] }>()

interface FilterPreset { name: string; filters: ActiveFilter[] }

const { t } = useI18n()
const activeFilters = ref<ActiveFilter[]>(props.initialFilters ?? [])

// Filter / presets popovers
const isFilterOpen = ref(false)
const filterAnchorEl = ref<HTMLElement | null>(null)
const isPresetsOpen = ref(false)
const presetsAnchorEl = ref<HTMLElement | null>(null)

const pickedField = ref<DocField | null>(null)
const pickedOp = ref('=')
const pickedValue = ref('')
const pickedDisplayValue = ref('')

// null = adding new; number = editing existing at that index
const editingIndex = ref<number | null>(null)

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
  if (!name || !activeFilters.value.length) return
  savedPresets.value = [...savedPresets.value.filter(p => p.name !== name), { name, filters: [...activeFilters.value] }]
  persistPresets()
  showSaveName.value = false
  presetNameInput.value = ''
}

function applyPreset(preset: FilterPreset) {
  activeFilters.value = [...preset.filters]
  emitChange()
  isPresetsOpen.value = false
}

function deletePreset(name: string) {
  savedPresets.value = savedPresets.value.filter(p => p.name !== name)
  persistPresets()
}

// ── Field list ──────────────────────────────────────────────────────────────
const filterableFields = computed(() =>
  props.fields.filter(f => f.in_filter && !['Section', 'Column', 'Tab'].includes(f.fieldtype))
)

// ── Pick field (new filter) ─────────────────────────────────────────────────
function pickField(f: DocField) {
  pickedField.value = f
  pickedOp.value = getFilterConfig(f.fieldtype).operators[0]
  pickedValue.value = ''
  pickedDisplayValue.value = ''
}

// ── Edit existing filter ───────────────────────────────────────────────────
function startEdit(i: number, event: Event) {
  const f = activeFilters.value[i]
  const field = props.fields.find(ff => ff.fieldname === f.fieldname) ?? null
  if (!field) return

  editingIndex.value = i
  pickedField.value = field
  pickedOp.value = f.op
  pickedValue.value = f.value
  pickedDisplayValue.value = f.displayValue ?? ''
  filterAnchorEl.value = event.currentTarget as HTMLElement
  isFilterOpen.value = true
}

function resetPopover() {
  pickedField.value = null
  pickedValue.value = ''
  pickedDisplayValue.value = ''
  editingIndex.value = null
}

// ── Add / save filter ────────────────────────────────────────────────────────
function applyFilter() {
  if (!pickedField.value || !pickedValue.value) return
  const entry: ActiveFilter = {
    fieldname: pickedField.value.fieldname,
    label: pickedField.value.label,
    fieldtype: pickedField.value.fieldtype,
    op: pickedOp.value,
    value: pickedValue.value,
    displayValue: pickedDisplayValue.value || undefined,
  }

  if (editingIndex.value !== null) {
    activeFilters.value.splice(editingIndex.value, 1, entry)
  } else {
    activeFilters.value.push(entry)
  }

  isFilterOpen.value = false
  emitChange()
}

function removeFilter(i: number) {
  activeFilters.value.splice(i, 1)
  emitChange()
}

function emitChange() {
  emit('change', activeFilters.value)
}

const OP_LABELS: Record<string, string> = {
  'child_of': '⊇',
}

function opLabel(op: string): string {
  return OP_LABELS[op] ?? op
}

function chipLabel(f: ActiveFilter): string {
  let val: string
  if (f.fieldtype === 'Check') {
    val = f.value === '1' ? 'Так' : 'Ні'
  } else {
    val = f.displayValue || f.value
  }
  return `${f.label} ${opLabel(f.op)} ${val}`
}

function toggleFilter(event: Event) {
    if (isFilterOpen.value) { isFilterOpen.value = false; return }
    filterAnchorEl.value = event.currentTarget as HTMLElement
    isFilterOpen.value = true
}

function togglePresets(event: Event) {
    if (isPresetsOpen.value) { isPresetsOpen.value = false; return }
    presetsAnchorEl.value = event.currentTarget as HTMLElement
    isPresetsOpen.value = true
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-2 mb-4">
    <!-- Active filter chips — click label to edit -->
    <Badge
      v-for="(f, i) in activeFilters"
      :key="i"
      variant="secondary"
      class="gap-0 pr-1 max-w-[240px] group/chip pl-0 overflow-hidden"
    >
      <button
        type="button"
        class="flex items-center gap-1.5 pl-2 pr-1.5 py-0.5 hover:bg-accent rounded-l-full transition-colors min-w-0"
        :title="'Редагувати фільтр'"
        @click="startEdit(i, $event)"
      >
        <Pencil class="size-2.5 shrink-0 opacity-0 group-hover/chip:opacity-60 transition-opacity" />
        <span class="truncate text-xs font-medium">{{ chipLabel(f) }}</span>
      </button>
      <button
        type="button"
        class="shrink-0 rounded-full hover:bg-muted-foreground/20 p-0.5 mr-0.5 transition-colors"
        @click="removeFilter(i)"
      >
        <X class="size-3" />
      </button>
    </Badge>

    <!-- Filter Popover -->
    <Button variant="outline" size="sm" class="h-7 border-dashed text-xs" @click="toggleFilter">
      <Filter class="size-3 mr-1" />
      {{ t('Filter') }}
    </Button>

    <Popover :open="isFilterOpen" @update:open="(v: boolean) => { isFilterOpen = v; if (!v) resetPopover() }">
      <PopoverAnchor :reference="filterAnchorEl ?? undefined" />
      <PopoverContent class="w-auto p-0">
      <div class="w-80 p-1">
        <!-- Step 1: pick field -->
        <template v-if="!pickedField">
          <p class="px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground/80 mb-1">
            {{ editingIndex !== null ? 'Змінити поле фільтру' : 'Поле для фільтрації' }}
          </p>
          <div class="flex flex-wrap gap-1 max-h-48 overflow-y-auto p-1 scrollbar-none">
            <Button
              v-for="f in filterableFields"
              :key="f.fieldname"
              type="button" variant="outline" size="sm"
              @click="pickField(f)"
            >{{ f.label }}</Button>
          </div>
          <p v-if="!filterableFields.length" class="text-xs text-muted-foreground mt-2 italic px-2">Немає полів з in_filter</p>
        </template>

        <!-- Step 2: set op + value -->
        <template v-else>
          <!-- Header -->
          <div class="flex items-center gap-2 mb-3 bg-muted/30 p-2 rounded-lg border border-border/40">
            <Button
              variant="ghost" size="icon" class="size-6"
              @click="pickedField = null; pickedValue = ''; pickedDisplayValue = ''"
            >
              <ChevronLeft />
            </Button>
            <span class="text-sm font-semibold text-foreground truncate">{{ pickedField.label }}</span>
            <span class="text-xs font-semibold uppercase tracking-wider text-muted-foreground/60 ml-auto">{{ pickedField.fieldtype }}</span>
          </div>

          <div class="space-y-4 p-1">
            <!-- Operator row -->
            <ToggleGroup
              type="single" variant="outline" size="sm" class="flex-wrap justify-start"
              :model-value="pickedOp" @update:model-value="(v: unknown) => v && (pickedOp = v as string)"
            >
              <ToggleGroupItem
                v-for="op in getFilterConfig(pickedField.fieldtype).operators"
                :key="op" :value="op" class="font-mono"
                :title="op === 'child_of' ? 'Включаючи всі підрозділи' : undefined"
              >{{ opLabel(op) }}</ToggleGroupItem>
            </ToggleGroup>

            <!-- Value input -->
            <div class="bg-muted/10 p-2 rounded-lg border border-border/40">
                <component
                    :is="getFilterConfig(pickedField.fieldtype).filterInput"
                    :field="pickedField"
                    :model-value="pickedValue"
                    :display-value="pickedDisplayValue"
                    :op="pickedOp"
                    @update:model-value="pickedValue = $event"
                    @update:display-value="pickedDisplayValue = $event"
                    @submit="applyFilter"
                />
            </div>

            <Button size="sm" class="w-full" :disabled="!pickedValue" @click="applyFilter">
                {{ editingIndex !== null ? 'Зберегти зміни' : t('Apply') }}
            </Button>
          </div>
        </template>
      </div>
      </PopoverContent>
    </Popover>

    <!-- Presets -->
    <template v-if="doctype">
      <template v-if="activeFilters.length">
        <template v-if="showSaveName">
          <div class="flex items-center gap-1 animate-in fade-in slide-in-from-left-2 duration-300">
            <Input
              v-model="presetNameInput"
              class="h-7 text-xs w-32"
              placeholder="Назва пресету"
              autofocus
              @keydown="(e: KeyboardEvent) => { if (e.key === 'Enter') savePreset(); else if (e.key === 'Escape') showSaveName = false }"
            />
            <Button size="sm" class="h-7 px-2.5 text-xs" @click="savePreset">OK</Button>
            <Button variant="ghost" size="icon" class="size-7" @click="showSaveName = false">
              <X class="size-3.5" />
            </Button>
          </div>
        </template>
        <Button variant="ghost" v-else size="sm" class="h-7 text-xs text-muted-foreground hover:text-foreground" @click="showSaveName = true">
          <Bookmark class="size-3 mr-1" />
          {{ t('Save') }}
        </Button>
      </template>

      <Button variant="ghost" v-if="savedPresets.length" size="sm" class="h-7 text-xs text-muted-foreground hover:text-foreground" @click="togglePresets">
        Пресети
        <ChevronDown class="size-3 ml-1" />
      </Button>

      <Popover v-model:open="isPresetsOpen">
        <PopoverAnchor :reference="presetsAnchorEl ?? undefined" />
        <PopoverContent class="w-60 p-1">
          <div class="px-2 py-1.5 text-xs font-medium text-muted-foreground">Збережені фільтри</div>
          <Separator class="my-1" />

          <div v-for="preset in savedPresets" :key="preset.name"
            class="flex items-center justify-between gap-2 p-2 rounded-md hover:bg-accent hover:text-accent-foreground cursor-pointer group/item"
            @click="applyPreset(preset)">
            <span class="text-xs font-medium truncate flex-1">{{ preset.name }}</span>
            <Button
              variant="ghost" size="icon" class="size-6 opacity-0 group-hover/item:opacity-100 hover:text-destructive"
              @click.stop="deletePreset(preset.name)"
            >
              <Trash2 class="size-3.5" />
            </Button>
          </div>
        </PopoverContent>
      </Popover>
    </template>
  </div>
</template>
