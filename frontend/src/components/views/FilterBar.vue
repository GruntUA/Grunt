<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DocField } from '@/types'

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
    <span
      v-for="(f, i) in activeFilters"
      :key="i"
      class="inline-flex items-center gap-1 px-2 py-1 bg-[--grunt-primary-light] text-[--grunt-primary] text-xs rounded-full"
    >
      <span>{{ f.label }} {{ f.op }} <b>{{ f.value }}</b></span>
      <button type="button" class="ml-1 hover:text-[--grunt-danger]" @click="removeFilter(i)">×</button>
    </span>

    <!-- Add filter button -->
    <div class="relative">
      <button
        type="button"
        class="inline-flex items-center gap-1 px-3 py-1.5 text-xs border border-dashed border-[--grunt-border] rounded-full text-[--grunt-text-secondary] hover:border-[--grunt-primary] hover:text-[--grunt-primary] transition-colors"
        @click="showDropdown = !showDropdown"
      >+ Фільтр</button>

      <!-- Dropdown -->
      <div
        v-if="showDropdown"
        class="absolute top-full mt-1 left-0 bg-[--grunt-surface] border border-[--grunt-border] rounded-[--grunt-radius-md] shadow-lg z-50 w-72 p-3 flex flex-col gap-2"
      >
        <p class="text-xs text-[--grunt-text-secondary] font-medium">Поле</p>
        <div class="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
          <button
            v-for="f in filterableFields"
            :key="f.fieldname"
            type="button"
            class="px-2 py-1 text-xs rounded border transition-colors"
            :class="pickedField?.fieldname === f.fieldname
              ? 'border-[--grunt-primary] bg-[--grunt-primary-light] text-[--grunt-primary]'
              : 'border-[--grunt-border] hover:border-[--grunt-primary]'"
            @click="pickField(f)"
          >{{ f.label }}</button>
        </div>

        <template v-if="pickedField">
          <div class="flex gap-2">
            <select v-model="pickedOp" class="flex-1 border border-[--grunt-border] rounded px-2 py-1 text-xs">
              <option v-for="op in OPS" :key="op" :value="op">{{ op }}</option>
            </select>
            <input
              v-model="pickedValue"
              class="flex-1 border border-[--grunt-border] rounded px-2 py-1 text-xs focus:outline-none focus:border-[--grunt-primary]"
              :placeholder="`Значення`"
              @keydown.enter="addFilter"
            />
          </div>
          <button
            type="button"
            class="w-full py-1.5 text-xs bg-[--grunt-primary] text-white rounded hover:bg-[--grunt-primary-hover] transition-colors"
            @click="addFilter"
          >Застосувати</button>
        </template>
        <p v-else-if="!filterableFields.length" class="text-xs text-[--grunt-text-muted]">Немає полів з in_filter=true</p>
      </div>
    </div>
  </div>
</template>
