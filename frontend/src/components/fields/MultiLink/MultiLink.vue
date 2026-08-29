<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
import { docsApi, metaApi } from '@/core/api'
import { X, Loader2 } from '@lucide/vue'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

// ── State ─────────────────────────────────────────────────────────────────────

const { t } = useI18n()
const query = ref('')
const results = ref<Record<string, string>[]>([])
const isOpen = ref(false)
const isLoading = ref(false)
const activeIdx = ref(-1)
const titleField = ref<string>('name')

// Resolved display labels: name → label
const displayLabels = ref<Map<string, string>>(new Map())

let debounceTimer: ReturnType<typeof setTimeout>
let blurTimer: ReturnType<typeof setTimeout>

// ── Selected values ─────────────────────────────────────────────────────────

const selectedValues = computed<string[]>(() => {
  const v = props.modelValue
  if (Array.isArray(v)) return v as string[]
  if (typeof v === 'string' && v) {
    try { return JSON.parse(v) as string[] } catch { return [] }
  }
  return []
})

// ── Resolve display labels ──────────────────────────────────────────────────

let titleFieldReady = false

async function resolveLabels(values: string[]) {
  if (!props.field.options || !titleFieldReady) return
  if (titleField.value === 'name') {
    values.forEach(v => displayLabels.value.set(v, v))
    return
  }
  for (const val of values) {
    if (displayLabels.value.has(val)) continue
    try {
      const doc = await docsApi.get(props.field.options, val)
      const label = (doc as Record<string, unknown>)[titleField.value]
      displayLabels.value.set(val, typeof label === 'string' && label ? label : val)
    } catch {
      displayLabels.value.set(val, val)
    }
  }
}

function getDisplayLabel(value: string): string {
  return displayLabels.value.get(value) ?? value
}

// ── Fetch linked DocType meta ───────────────────────────────────────────────

watch(() => props.field.options, async (doctype) => {
  if (!doctype) return
  try {
    const meta = await metaApi.get(doctype)
    titleField.value = meta.title_field || 'name'
  } catch {
    titleField.value = 'name'
  }
  titleFieldReady = true
  displayLabels.value.clear()
  if (selectedValues.value.length) resolveLabels(selectedValues.value)
}, { immediate: true })

watch(selectedValues, (vals) => {
  if (vals.length) resolveLabels(vals)
})

// ── Search ────────────────────────────────────────────────────────────────────

const filteredResults = computed(() =>
  results.value.filter(r => !selectedValues.value.includes(r.name))
)

async function search(val: string) {
  if (!props.field.options) return
  isLoading.value = true
  try {
    const fields = titleField.value !== 'name'
      ? `id,name,${titleField.value}`
      : 'id,name'
    const resp = await docsApi.list(props.field.options, {
      search: val || undefined,
      per_page: 20,
      fields,
    })
    results.value = (resp.data ?? []) as Record<string, string>[]
    activeIdx.value = -1
    isOpen.value = true
  } catch {
    results.value = []
  } finally {
    isLoading.value = false
  }
}

function onInput(val: string) {
  query.value = val
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(val), val ? 300 : 0)
}

function onFocus() {
  clearTimeout(blurTimer)
  if (!isOpen.value) search(query.value)
}

function onBlur() {
  blurTimer = setTimeout(() => {
    isOpen.value = false
    query.value = ''
  }, 200)
}

// ── Keyboard navigation ───────────────────────────────────────────────────────

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Backspace' && !query.value && selectedValues.value.length) {
    e.preventDefault()
    removeValue(selectedValues.value[selectedValues.value.length - 1])
    return
  }

  if (!isOpen.value) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIdx.value = Math.min(activeIdx.value + 1, filteredResults.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIdx.value = Math.max(activeIdx.value - 1, -1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (activeIdx.value >= 0 && filteredResults.value[activeIdx.value]) {
      addItem(filteredResults.value[activeIdx.value])
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    isOpen.value = false
    query.value = ''
  }
}

// ── Selection ─────────────────────────────────────────────────────────────────

function addItem(item: Record<string, string>) {
  const name = item.name
  if (selectedValues.value.includes(name)) return

  const label = titleField.value !== 'name' && item[titleField.value]
    ? item[titleField.value]
    : item.name
  displayLabels.value.set(name, label)

  const newValues = [...selectedValues.value, name]
  emit('update:modelValue', newValues)
  query.value = ''
  // Keep dropdown open for adding more
  search('')
}

function removeValue(name: string) {
  const newValues = selectedValues.value.filter(v => v !== name)
  emit('update:modelValue', newValues)
}

// ── Display helpers ───────────────────────────────────────────────────────────

function getLabel(item: Record<string, string>): string {
  if (titleField.value !== 'name' && item[titleField.value]) return item[titleField.value]
  return item.name
}

function getSublabel(item: Record<string, string>): string | null {
  if (titleField.value !== 'name' && item[titleField.value] && item[titleField.value] !== item.name) {
    return item.name
  }
  return null
}

function highlight(text: string): string {
  if (!query.value.trim()) return text
  const escaped = query.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(new RegExp(`(${escaped})`, 'gi'), '<mark class="bg-primary/20 text-foreground rounded-sm">$1</mark>')
}
</script>

<template>
  <div class="relative">
    <!-- Tags + Input wrapper -->
    <div
      class="flex flex-wrap items-center gap-1.5 min-h-[38px] w-full rounded-md border border-input bg-transparent px-2 py-1.5 ring-offset-background transition-colors focus-within:ring-2 focus-within:ring-ring focus-within:border-ring"
      :class="{
        'border-destructive focus-within:ring-destructive': error,
        'bg-muted cursor-not-allowed': disabled || field.read_only,
      }"
      @click="($refs.inputEl as HTMLInputElement)?.focus()"
    >
      <!-- Tags -->
      <span
        v-for="val in selectedValues"
        :key="val"
        class="inline-flex items-center gap-1 rounded-md bg-secondary text-secondary-foreground px-2 py-0.5 max-w-[200px]"
      >
        <span class="truncate">{{ getDisplayLabel(val) }}</span>
        <button
          v-if="!disabled && !field.read_only"
          type="button"
          class="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          @mousedown.prevent="removeValue(val)"
        >
          <X class="size-3" />
        </button>
      </span>

      <!-- Input -->
      <div v-if="!disabled && !field.read_only" class="relative flex-1 min-w-[120px]">
        <input
          ref="inputEl"
          :value="query"
          :placeholder="selectedValues.length ? '' : (field.placeholder ?? t('Search {doctype}...', { doctype: field.options ?? '' }))"
          class="w-full bg-transparent outline-none py-0.5"
          autocomplete="off"
          @input="onInput(($event.target as HTMLInputElement).value)"
          @focus="onFocus"
          @blur="onBlur"
          @keydown="onKeydown"
        />
      </div>

      <!-- Loading indicator -->
      <Loader2 v-if="isLoading" class="size-4 text-muted-foreground animate-spin shrink-0" />
    </div>

    <!-- Dropdown -->
    <div
      v-if="isOpen && !disabled && !field.read_only"
      class="absolute top-full mt-1 left-0 right-0 bg-popover border border-border rounded-lg shadow-md z-50 overflow-hidden"
    >
      <template v-if="filteredResults.length">
        <div class="max-h-52 overflow-y-auto py-1">
          <button
            v-for="(item, i) in filteredResults"
            :key="item.id"
            type="button"
            :class="[
              'w-full text-left px-3 py-2 text-sm transition-colors flex flex-col gap-0.5',
              i === activeIdx ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
            ]"
            @mousedown.prevent="addItem(item)"
            @mouseover="activeIdx = i"
          >
            <span v-html="highlight(getLabel(item))" />
            <span v-if="getSublabel(item)" class="text-xs text-muted-foreground" v-html="highlight(getSublabel(item)!)" />
          </button>
        </div>
      </template>

      <div v-else class="px-3 py-3 text-muted-foreground text-center">
        <span v-if="isLoading">{{ t('Searching...') }}</span>
        <span v-else-if="query">{{ t('Nothing found for «{query}»', { query }) }}</span>
        <span v-else>{{ t('No records') }}</span>
      </div>
    </div>
  </div>
</template>
