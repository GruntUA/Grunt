<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DocField } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Filter, X } from 'lucide-vue-next'

const props = defineProps<{
  fields: DocField[]
}>()

const emit = defineEmits<{ change: [filters: Record<string, string>] }>()

interface ActiveFilter { fieldname: string; label: string; op: string; value: string }

const activeFilters = ref<ActiveFilter[]>([])
const showDropdown = ref(false)
const pickedField = ref<DocField | null>(null)
const pickedOp = ref('=')
const pickedValue = ref('')

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
          Фільтр
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
          <Button size="sm" class="w-full mt-2" @click="addFilter">Застосувати</Button>
        </template>
        <p v-else-if="!filterableFields.length" class="text-xs text-muted-foreground mt-2">Немає полів для фільтрації</p>
      </PopoverContent>
    </Popover>
  </div>
</template>
