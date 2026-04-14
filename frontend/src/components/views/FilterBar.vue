<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField, ActiveFilter } from '@/types'
import type { LinkSearchItem } from '@/core/api/docs'
import { docsApi } from '@/core/api/docs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Filter, X, Bookmark, ChevronDown, Trash2, Loader2, Pencil } from 'lucide-vue-next'

const props = defineProps<{
  fields: DocField[]
  doctype?: string
}>()

const emit = defineEmits<{ change: [filters: ActiveFilter[]] }>()

interface FilterPreset { name: string; filters: ActiveFilter[] }

const { t } = useI18n()
const activeFilters = ref<ActiveFilter[]>([])
const showDropdown = ref(false)
const pickedField = ref<DocField | null>(null)
const pickedOp = ref('=')
const pickedValue = ref('')
const pickedDisplayValue = ref('')

// null = adding new; number = editing existing at that index
const editingIndex = ref<number | null>(null)

// ── Ops per field type ──────────────────────────────────────────────────────
const TEXT_OPS  = ['=', '!=', 'like']
const NUM_OPS   = ['=', '!=', '>', '<', '>=', '<=']
const DATE_OPS  = ['=', '!=', '>', '<', '>=', '<=']
const LINK_OPS  = ['=', '!=']
const CHECK_OPS = ['=']

function opsFor(fieldtype: string): string[] {
  if (['Int', 'Float', 'Currency', 'Rating'].includes(fieldtype)) return NUM_OPS
  if (['Date', 'Datetime', 'Time'].includes(fieldtype)) return DATE_OPS
  if (fieldtype === 'Check') return CHECK_OPS
  if (fieldtype === 'Link') return LINK_OPS
  return TEXT_OPS
}

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
  pickedOp.value = opsFor(f.fieldtype)[0]
  pickedValue.value = ''
  pickedDisplayValue.value = ''
  linkQuery.value = ''
  linkResults.value = []
}

// ── Edit existing filter ────────────────────────────────────────────────────
function startEdit(i: number) {
  const f = activeFilters.value[i]
  const field = props.fields.find(ff => ff.fieldname === f.fieldname) ?? null
  if (!field) return

  editingIndex.value = i
  pickedField.value = field
  pickedOp.value = f.op
  pickedValue.value = f.value
  pickedDisplayValue.value = f.displayValue ?? ''

  if (field.fieldtype === 'Link') {
    _suppressLinkClear.value = true
    linkQuery.value = f.displayValue || f.value
    nextTick(() => { _suppressLinkClear.value = false })
  } else {
    linkQuery.value = ''
    linkResults.value = []
  }

  showDropdown.value = true
}

// ── Parsed Select options ───────────────────────────────────────────────────
const selectOptions = computed(() => {
  const f = pickedField.value
  if (!f || f.fieldtype !== 'Select' || !f.options) return []
  return typeof f.options === 'string'
    ? f.options.split('\n').map(o => o.trim()).filter(Boolean)
    : (f.options as string[])
})

// ── Link field search ───────────────────────────────────────────────────────
const linkQuery = ref('')
const linkResults = ref<LinkSearchItem[]>([])
const linkLoading = ref(false)
const _suppressLinkClear = ref(false)

let linkDebounce: ReturnType<typeof setTimeout>
watch(linkQuery, (q) => {
  if (_suppressLinkClear.value) return
  clearTimeout(linkDebounce)
  pickedValue.value = ''
  pickedDisplayValue.value = ''
  if (!q.trim()) { linkResults.value = []; return }
  linkDebounce = setTimeout(() => searchLinks(q), 280)
})

async function searchLinks(q: string) {
  const linkedDoctype = pickedField.value?.options
  if (!linkedDoctype || typeof linkedDoctype !== 'string') return
  linkLoading.value = true
  try {
    linkResults.value = await docsApi.linkSearch(linkedDoctype, q)
  } catch {
    linkResults.value = []
  } finally {
    linkLoading.value = false
  }
}

function selectLinkItem(item: LinkSearchItem) {
  pickedValue.value = item.name
  pickedDisplayValue.value = item.title || item.name
  linkQuery.value = item.title || item.name
  linkResults.value = []
}

// ── Reset popover state ─────────────────────────────────────────────────────
function resetPopover() {
  pickedField.value = null
  pickedValue.value = ''
  pickedDisplayValue.value = ''
  linkQuery.value = ''
  linkResults.value = []
  editingIndex.value = null
}

// Clear state when popover closes
watch(showDropdown, (open) => {
  if (!open) resetPopover()
})

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

  showDropdown.value = false
  emitChange()
}

function removeFilter(i: number) {
  activeFilters.value.splice(i, 1)
  emitChange()
}

function emitChange() {
  emit('change', activeFilters.value)
}

// ── Chip label ──────────────────────────────────────────────────────────────
function chipLabel(f: ActiveFilter): string {
  let val: string
  if (f.fieldtype === 'Check') {
    val = f.value === '1' ? 'Так' : 'Ні'
  } else {
    val = f.displayValue || f.value
  }
  return `${f.label} ${f.op} ${val}`
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
        class="flex items-center gap-1.5 pl-2 pr-1.5 py-0.5 hover:bg-primary/10 rounded-l-full transition-colors min-w-0"
        :title="'Редагувати фільтр'"
        @click="startEdit(i)"
      >
        <Pencil class="size-2.5 shrink-0 opacity-0 group-hover/chip:opacity-60 transition-opacity text-primary" />
        <span class="truncate text-xs">{{ chipLabel(f) }}</span>
      </button>
      <button
        type="button"
        class="shrink-0 rounded-full hover:bg-muted-foreground/20 p-0.5 mr-0.5 transition-colors"
        @click="removeFilter(i)"
      >
        <X class="size-3" />
      </button>
    </Badge>

    <!-- Add filter / edit popover -->
    <Popover v-model:open="showDropdown">
      <PopoverTrigger as-child>
        <Button
          variant="ghost"
          size="sm"
          class="h-7 text-xs border border-dashed border-border text-muted-foreground hover:text-foreground hover:border-primary/50"
        >
          <Filter class="size-3 mr-1" />
          {{ t('Filter') }}
        </Button>
      </PopoverTrigger>
      <PopoverContent class="w-80 p-3" align="start">

        <!-- Step 1: pick field -->
        <template v-if="!pickedField">
          <p class="text-xs font-semibold text-muted-foreground mb-2">
            {{ editingIndex !== null ? 'Змінити поле фільтру' : 'Поле для фільтрації' }}
          </p>
          <div class="flex flex-wrap gap-1 max-h-36 overflow-y-auto">
            <button
              v-for="f in filterableFields"
              :key="f.fieldname"
              type="button"
              class="px-2 py-1 text-xs rounded-md border border-border hover:border-primary/50 hover:bg-primary/5 transition-colors"
              @click="pickField(f)"
            >{{ f.label }}</button>
          </div>
          <p v-if="!filterableFields.length" class="text-xs text-muted-foreground mt-2 italic">Немає полів з in_filter</p>
        </template>

        <!-- Step 2: set op + value -->
        <template v-else>
          <!-- Header -->
          <div class="flex items-center gap-2 mb-3">
            <button
              type="button"
              class="text-muted-foreground hover:text-foreground transition-colors"
              @click="pickedField = null; pickedValue = ''; pickedDisplayValue = ''"
            >
              <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>
            </button>
            <span class="text-sm font-semibold text-foreground">{{ pickedField.label }}</span>
            <span class="text-xs text-muted-foreground ml-auto">{{ pickedField.fieldtype }}</span>
          </div>

          <!-- Operator row -->
          <div class="flex gap-1 mb-3 flex-wrap">
            <button
              v-for="op in opsFor(pickedField.fieldtype)"
              :key="op"
              type="button"
              class="px-2 py-0.5 text-xs rounded border transition-colors font-mono"
              :class="pickedOp === op
                ? 'border-primary bg-primary/10 text-primary font-semibold'
                : 'border-border hover:border-primary/40 text-muted-foreground'"
              @click="pickedOp = op"
            >{{ op }}</button>
          </div>

          <!-- Value: Select — option buttons -->
          <template v-if="pickedField.fieldtype === 'Select'">
            <div class="flex flex-wrap gap-1 max-h-32 overflow-y-auto mb-3">
              <button
                v-for="opt in selectOptions"
                :key="opt"
                type="button"
                class="px-2 py-1 text-xs rounded-md border transition-colors"
                :class="pickedValue === opt
                  ? 'border-primary bg-primary/10 text-primary font-semibold'
                  : 'border-border hover:border-primary/40'"
                @click="pickedValue = opt"
              >{{ opt }}</button>
            </div>
          </template>

          <!-- Value: Check — Yes/No toggle -->
          <template v-else-if="pickedField.fieldtype === 'Check'">
            <div class="flex gap-2 mb-3">
              <button
                type="button"
                class="flex-1 py-1.5 text-xs rounded border transition-colors"
                :class="pickedValue === '1'
                  ? 'border-primary bg-primary/10 text-primary font-semibold'
                  : 'border-border hover:border-primary/40 text-muted-foreground'"
                @click="pickedValue = '1'"
              >✓ Так</button>
              <button
                type="button"
                class="flex-1 py-1.5 text-xs rounded border transition-colors"
                :class="pickedValue === '0'
                  ? 'border-primary bg-primary/10 text-primary font-semibold'
                  : 'border-border hover:border-primary/40 text-muted-foreground'"
                @click="pickedValue = '0'"
              >✗ Ні</button>
            </div>
          </template>

          <!-- Value: Link — live search -->
          <template v-else-if="pickedField.fieldtype === 'Link'">
            <div class="mb-3 space-y-1.5">
              <div class="relative">
                <Input
                  v-model="linkQuery"
                  class="h-8 text-xs pr-7"
                  :placeholder="`Пошук ${pickedField.options}...`"
                  @keydown.enter.prevent="linkResults[0] && selectLinkItem(linkResults[0])"
                />
                <Loader2 v-if="linkLoading" class="absolute right-2 top-1/2 -translate-y-1/2 size-3.5 animate-spin text-muted-foreground" />
              </div>
              <div v-if="linkResults.length" class="border border-border rounded-md overflow-hidden max-h-40 overflow-y-auto divide-y divide-border/60">
                <button
                  v-for="item in linkResults"
                  :key="item.id"
                  type="button"
                  class="w-full px-3 py-2 text-left text-xs hover:bg-primary/5 transition-colors flex items-center gap-2"
                  :class="pickedValue === item.name ? 'bg-primary/10' : ''"
                  @click="selectLinkItem(item)"
                >
                  <span class="font-medium text-foreground truncate flex-1">{{ item.title || item.name }}</span>
                  <span v-if="item.subtitle" class="text-muted-foreground/60 shrink-0 truncate max-w-[80px]">{{ item.subtitle }}</span>
                </button>
              </div>
              <p v-else-if="linkQuery && !linkLoading" class="text-xs text-muted-foreground/60 italic px-1">
                Нічого не знайдено
              </p>
              <div v-if="pickedValue" class="flex items-center gap-1.5 px-2 py-1 bg-primary/5 border border-primary/20 rounded-md text-xs text-primary">
                <span class="truncate flex-1">{{ pickedDisplayValue || pickedValue }}</span>
                <button type="button" class="shrink-0 hover:text-destructive" @click="pickedValue = ''; pickedDisplayValue = ''; linkQuery = ''">
                  <X class="size-3" />
                </button>
              </div>
            </div>
          </template>

          <!-- Value: Date / Datetime -->
          <template v-else-if="['Date', 'Datetime'].includes(pickedField.fieldtype)">
            <Input
              v-model="pickedValue"
              :type="pickedField.fieldtype === 'Datetime' ? 'datetime-local' : 'date'"
              class="h-8 text-xs mb-3"
              @keydown.enter="applyFilter"
            />
          </template>

          <!-- Value: plain text -->
          <template v-else>
            <Input
              v-model="pickedValue"
              class="h-8 text-xs mb-3"
              :placeholder="pickedOp === 'like' ? 'частина тексту...' : 'Значення'"
              @keydown.enter="applyFilter"
            />
          </template>

          <Button size="sm" class="w-full" :disabled="!pickedValue" @click="applyFilter">
            {{ editingIndex !== null ? 'Зберегти зміни' : t('Apply') }}
          </Button>
        </template>
      </PopoverContent>
    </Popover>

    <!-- Save/Load presets -->
    <template v-if="doctype">
      <template v-if="activeFilters.length">
        <template v-if="showSaveName">
          <div class="flex items-center gap-1">
            <Input
              v-model="presetNameInput"
              class="h-7 text-xs w-28"
              placeholder="Назва пресету"
              autofocus
              @keydown.enter="savePreset"
              @keydown.escape="showSaveName = false"
            />
            <Button size="sm" class="h-7 px-2 text-xs" @click="savePreset">OK</Button>
            <button type="button" class="text-muted-foreground hover:text-foreground" @click="showSaveName = false">
              <X class="size-3.5" />
            </button>
          </div>
        </template>
        <Button v-else variant="ghost" size="sm" class="h-7 text-xs text-muted-foreground hover:text-foreground" @click="showSaveName = true">
          <Bookmark class="size-3 mr-1" />
          {{ t('Save') }}
        </Button>
      </template>

      <DropdownMenu v-if="savedPresets.length">
        <DropdownMenuTrigger as-child>
          <Button variant="ghost" size="sm" class="h-7 text-xs text-muted-foreground hover:text-foreground">
            Пресети
            <ChevronDown class="size-3 ml-1" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" class="w-52">
          <DropdownMenuLabel class="text-xs">Збережені фільтри</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            v-for="preset in savedPresets"
            :key="preset.name"
            class="flex items-center justify-between gap-2 group/item"
            @select.prevent="applyPreset(preset)"
          >
            <span class="text-sm truncate flex-1">{{ preset.name }}</span>
            <button
              type="button"
              class="opacity-0 group-hover/item:opacity-100 text-muted-foreground hover:text-destructive transition-all"
              @click.stop="deletePreset(preset.name)"
            >
              <Trash2 class="size-3.5" />
            </button>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>
  </div>
</template>
