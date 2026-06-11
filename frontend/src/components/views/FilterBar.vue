<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField, ActiveFilter } from '@/types'
import { Filter, X, Bookmark, ChevronDown, Trash2, Pencil } from '@lucide/vue'
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

// PrimeVue Overlay refs
const opFilter = ref()
const opPresets = ref()

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
  opPresets.value?.hide()
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
  opFilter.value?.show(event)
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

  opFilter.value?.hide()
  emitChange()
}

function removeFilter(i: number) {
  activeFilters.value.splice(i, 1)
  emitChange()
}

function emitChange() {
  emit('change', activeFilters.value)
}

function chipLabel(f: ActiveFilter): string {
  let val: string
  if (f.fieldtype === 'Check') {
    val = f.value === '1' ? 'Так' : 'Ні'
  } else {
    val = f.displayValue || f.value
  }
  return `${f.label} ${f.op} ${val}`
}

function toggleFilter(event: Event) {
    opFilter.value?.toggle(event)
}

function togglePresets(event: Event) {
    opPresets.value?.toggle(event)
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-2 mb-4">
    <!-- Active filter chips — click label to edit -->
    <Badge
      v-for="(f, i) in activeFilters"
      :key="i"
      severity="secondary"
      class="gap-0 pr-1 max-w-[240px] group/chip pl-0 overflow-hidden shadow-sm border-border/40"
    >
      <button
        type="button"
        class="flex items-center gap-1.5 pl-2 pr-1.5 py-0.5 hover:bg-primary/10 rounded-l-full transition-colors min-w-0"
        :title="'Редагувати фільтр'"
        @click="startEdit(i, $event)"
      >
        <Pencil class="size-2.5 shrink-0 opacity-0 group-hover/chip:opacity-60 transition-opacity text-primary" />
        <span class="truncate text-[11px] font-medium">{{ chipLabel(f) }}</span>
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
    <Button text size="small"
      class="h-7 text-[11px] border border-dashed border-border text-muted-foreground hover:text-foreground hover:border-primary/50 transition-all font-medium"
      @click="toggleFilter"
    >
      <Filter class="size-3 mr-1" />
      {{ t('Filter') }}
    </Button>

    <Popover ref="opFilter" @hide="resetPopover">
      <div class="w-80 p-1">
        <!-- Step 1: pick field -->
        <template v-if="!pickedField">
          <p class="px-2 py-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground/80 mb-1">
            {{ editingIndex !== null ? 'Змінити поле фільтру' : 'Поле для фільтрації' }}
          </p>
          <div class="flex flex-wrap gap-1 max-h-48 overflow-y-auto p-1 scrollbar-none">
            <button
              v-for="f in filterableFields"
              :key="f.fieldname"
              type="button"
              class="px-2.5 py-1.5 text-xs rounded-lg border border-border/60 bg-muted/20 hover:border-primary/50 hover:bg-primary/5 hover:text-primary transition-all font-medium"
              @click="pickField(f)"
            >{{ f.label }}</button>
          </div>
          <p v-if="!filterableFields.length" class="text-xs text-muted-foreground mt-2 italic px-2">Немає полів з in_filter</p>
        </template>

        <!-- Step 2: set op + value -->
        <template v-else>
          <!-- Header -->
          <div class="flex items-center gap-2 mb-3 bg-muted/30 p-2 rounded-lg border border-border/40">
            <button
              type="button"
              class="size-6 p-0 border-none bg-transparent flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
              @click="pickedField = null; pickedValue = ''; pickedDisplayValue = ''"
            >
              <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
            </button>
            <span class="text-sm font-bold text-foreground truncate">{{ pickedField.label }}</span>
            <span class="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/60 ml-auto">{{ pickedField.fieldtype }}</span>
          </div>

          <div class="space-y-4 p-1">
            <!-- Operator row -->
            <div class="flex gap-1.5 flex-wrap">
              <button
                v-for="op in getFilterConfig(pickedField.fieldtype).operators"
                :key="op"
                type="button"
                class="px-2.5 py-1.5 text-[11px] rounded-lg border transition-all font-bold font-mono shadow-sm"
                :class="pickedOp === op
                  ? 'border-primary bg-primary/10 text-primary shadow-inner'
                  : 'border-border/60 bg-card hover:border-primary/40 text-muted-foreground'"
                @click="pickedOp = op"
              >{{ op }}</button>
            </div>

            <!-- Value input -->
            <div class="bg-muted/10 p-2 rounded-xl border border-border/40 shadow-inner">
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

            <Button size="small" class="w-full h-10 shadow-lg shadow-primary/10" :disabled="!pickedValue" @click="applyFilter">
                {{ editingIndex !== null ? 'Зберегти зміни' : t('Apply') }}
            </Button>
          </div>
        </template>
      </div>
    </Popover>

    <!-- Presets -->
    <template v-if="doctype">
      <template v-if="activeFilters.length">
        <template v-if="showSaveName">
          <div class="flex items-center gap-1 animate-in fade-in slide-in-from-left-2 duration-300">
            <InputText
              v-model="presetNameInput"
              class="h-7 text-[11px] w-32 rounded-lg"
              placeholder="Назва пресету"
              autofocus
              @keydown="(e: KeyboardEvent) => { if (e.key === 'Enter') savePreset(); else if (e.key === 'Escape') showSaveName = false }"
            />
            <Button size="small" class="h-7 px-2.5 text-[11px] shadow-sm" @click="savePreset">OK</Button>
            <button type="button" class="text-muted-foreground hover:text-foreground p-1 transition-colors" @click="showSaveName = false">
              <X class="size-3.5" />
            </button>
          </div>
        </template>
        <Button v-else text size="small" class="h-7 text-[11px] text-muted-foreground hover:text-foreground font-medium transition-all" @click="showSaveName = true">
          <Bookmark class="size-3 mr-1" />
          {{ t('Save') }}
        </Button>
      </template>

      <Button v-if="savedPresets.length" text size="small" 
        class="h-7 text-[11px] text-muted-foreground hover:text-foreground font-medium transition-all"
        @click="togglePresets">
        Пресети
        <ChevronDown class="size-3 ml-1" />
      </Button>

      <Popover ref="opPresets">
        <div class="w-60 p-1">
          <div class="px-2 py-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground/80">Збережені фільтри</div>
          <div class="h-px bg-border/40 my-1" />
          
          <div v-for="preset in savedPresets" :key="preset.name"
            class="flex items-center justify-between gap-2 p-2 rounded-lg hover:bg-muted/50 cursor-pointer group/item transition-all"
            @click="applyPreset(preset)">
            <span class="text-xs font-semibold truncate flex-1">{{ preset.name }}</span>
            <button
              type="button"
              class="size-6 flex items-center justify-center rounded-md opacity-0 group-hover/item:opacity-100 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all shadow-sm"
              @click.stop="deletePreset(preset.name)"
            >
              <Trash2 class="size-3.5" />
            </button>
          </div>
        </div>
      </Popover>
    </template>
  </div>
</template>
