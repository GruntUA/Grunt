<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
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
import { Filter, X, Bookmark, ChevronDown, Trash2 } from 'lucide-vue-next'

const props = defineProps<{
  fields: DocField[]
  doctype?: string
}>()

const emit = defineEmits<{ change: [filters: Record<string, string>] }>()

interface ActiveFilter { fieldname: string; label: string; op: string; value: string }
interface FilterPreset { name: string; filters: ActiveFilter[] }

const { t } = useI18n()
const activeFilters = ref<ActiveFilter[]>([])
const showDropdown = ref(false)
const pickedField = ref<DocField | null>(null)
const pickedOp = ref('=')
const pickedValue = ref('')

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
  } catch {
    return []
  }
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

const filterableFields = computed(() =>
  props.fields.filter((f) => f.in_filter && !['Section', 'Column', 'Tab'].includes(f.fieldtype))
)

const OPS = ['=', '!=', 'like', '>', '<', '>=', '<=']

function pickField(f: DocField) {
  pickedField.value = f
  pickedOp.value = '='
  pickedValue.value = ''
}

function addFilter() {
  if (!pickedField.value || !pickedValue.value) return
  activeFilters.value.push({
    fieldname: pickedField.value.fieldname,
    label: pickedField.value.label,
    op: pickedOp.value,
    value: pickedValue.value,
  })
  pickedField.value = null
  pickedValue.value = ''
  showDropdown.value = false
  emitChange()
}

function removeFilter(i: number) {
  activeFilters.value.splice(i, 1)
  emitChange()
}

function emitChange() {
  const filters: Record<string, string> = {}
  for (const f of activeFilters.value) {
    filters[f.fieldname] = f.value
  }
  emit('change', filters)
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-2 mb-4">
    <!-- Active filter chips -->
    <Badge
      v-for="(f, i) in activeFilters"
      :key="i"
      variant="secondary"
      class="gap-1 pr-1"
    >
      <span>{{ f.label }} {{ f.op }} <b>{{ f.value }}</b></span>
      <button type="button" class="ml-0.5 rounded-full hover:bg-muted-foreground/20 p-0.5 transition-colors" @click="removeFilter(i)">
        <X class="size-3" />
      </button>
    </Badge>

    <!-- Add filter button -->
    <Popover v-model:open="showDropdown">
      <PopoverTrigger as-child>
        <Button variant="ghost" size="sm" class="h-7 text-xs border border-dashed border-border text-muted-foreground hover:text-foreground hover:border-primary/50">
          <Filter class="size-3 mr-1" />
          {{ t('Filter') }}
        </Button>
      </PopoverTrigger>
      <PopoverContent class="w-72 p-3" align="start">
        <p class="text-xs font-medium text-muted-foreground mb-2">Поле</p>
        <div class="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
          <button
            v-for="f in filterableFields"
            :key="f.fieldname"
            type="button"
            class="px-2 py-1 text-xs rounded-md border transition-colors"
            :class="pickedField?.fieldname === f.fieldname
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-border hover:border-primary/50'"
            @click="pickField(f)"
          >{{ f.label }}</button>
        </div>

        <template v-if="pickedField">
          <div class="flex gap-2 mt-3">
            <select v-model="pickedOp" class="flex-1 border border-input rounded-md px-2 py-1.5 text-xs bg-transparent focus:outline-none focus:ring-1 focus:ring-ring">
              <option v-for="op in OPS" :key="op" :value="op">{{ op }}</option>
            </select>
            <Input
              v-model="pickedValue"
              class="flex-1 h-7 text-xs"
              placeholder="Значення"
              @keydown.enter="addFilter"
            />
          </div>
          <Button size="sm" class="w-full mt-2" @click="addFilter">{{ t('Apply') }}</Button>
        </template>
        <p v-else-if="!filterableFields.length" class="text-xs text-muted-foreground mt-2">Немає полів для фільтрації</p>
      </PopoverContent>
    </Popover>

    <!-- Save/Load presets (only when doctype provided) -->
    <template v-if="doctype">
      <!-- Save current filters as preset -->
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

      <!-- Load presets dropdown -->
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
