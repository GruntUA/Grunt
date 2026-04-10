<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
import { docsApi, metaApi } from '@/core/api'
import { Search, X, Loader2 } from 'lucide-vue-next'

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

// Cache: name → display label
const displayCache = new Map<string, string>()

let debounceTimer: ReturnType<typeof setTimeout>
let blurTimer: ReturnType<typeof setTimeout>

// ── Resolve display label for a stored value ─────────────────────────────────

async function resolveDisplay(value: string): Promise<string> {
  if (!value || !props.field.options) return value
  if (displayCache.has(value)) return displayCache.get(value)!

  if (titleField.value === 'name') {
    displayCache.set(value, value)
    return value
  }

  try {
    const doc = await docsApi.get(props.field.options, value)
    const label = (doc as Record<string, unknown>)[titleField.value]
    const display = typeof label === 'string' && label ? label : value
    displayCache.set(value, display)
    return display
  } catch {
    displayCache.set(value, value)
    return value
  }
}

async function syncQueryFromValue(v: unknown) {
  const raw = String(v ?? '')
  if (!raw) { query.value = ''; return }
  query.value = raw // show raw immediately to avoid blank
  query.value = await resolveDisplay(raw)
}

// ── Sync value → display ──────────────────────────────────────────────────────

watch(() => props.modelValue, (v) => {
  syncQueryFromValue(v)
})

// Fetch linked DocType meta to get title_field
watch(() => props.field.options, async (doctype) => {
  if (!doctype) return
  try {
    const meta = await metaApi.get(doctype)
    titleField.value = meta.title_field || 'name'
  } catch {
    titleField.value = 'name'
  }
  // Re-resolve display after title_field is known
  if (props.modelValue) syncQueryFromValue(props.modelValue)
}, { immediate: true })

// ── Search ────────────────────────────────────────────────────────────────────

async function search(val: string) {
  if (!props.field.options) return
  isLoading.value = true
  try {
    const fields = titleField.value !== 'name'
      ? `id,name,${titleField.value}`
      : 'id,name'
    const resp = await docsApi.list(props.field.options, {
      search: val || undefined,
      per_page: 10,
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
  // Don't emit yet — only emit when item is selected
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(val), val ? 300 : 0)
}

function onFocus() {
  clearTimeout(blurTimer)
  // Show results immediately on focus
  if (!isOpen.value) search(query.value)
}

function onBlur() {
  blurTimer = setTimeout(() => {
    isOpen.value = false
    // If user typed something but didn't select — restore previous display
    syncQueryFromValue(props.modelValue)
  }, 200)
}

// ── Keyboard navigation ───────────────────────────────────────────────────────

function onKeydown(e: KeyboardEvent) {
  if (!isOpen.value) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIdx.value = Math.min(activeIdx.value + 1, results.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIdx.value = Math.max(activeIdx.value - 1, -1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (activeIdx.value >= 0 && results.value[activeIdx.value]) {
      select(results.value[activeIdx.value])
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    isOpen.value = false
    syncQueryFromValue(props.modelValue)
  }
}

// ── Selection ─────────────────────────────────────────────────────────────────

function select(item: Record<string, string>) {
  const value = item.name
  const display = titleField.value !== 'name' && item[titleField.value]
    ? item[titleField.value]
    : item.name
  query.value = display
  emit('update:modelValue', value)
  isOpen.value = false
}

function clear() {
  query.value = ''
  emit('update:modelValue', null)
  isOpen.value = false
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

// Highlight matched part in text
function highlight(text: string): string {
  if (!query.value.trim()) return text
  const escaped = query.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(new RegExp(`(${escaped})`, 'gi'), '<mark class="bg-primary/20 text-foreground rounded-sm">$1</mark>')
}

const isSelected = computed(() => props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== '')
</script>

<template>
  <div class="relative">
    <!-- Input -->
    <div class="relative">
      <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />

      <input
        :value="query"
        :placeholder="field.placeholder ?? t('Search {doctype}...', { doctype: field.options ?? '' })"
        :disabled="disabled || field.read_only"
        class="w-full rounded-md border border-input bg-transparent pl-8 pr-8 py-2 text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-ring disabled:bg-muted disabled:cursor-not-allowed transition-colors"
        :class="{ 'border-destructive focus-visible:ring-destructive': error }"
        autocomplete="off"
        @input="onInput(($event.target as HTMLInputElement).value)"
        @focus="onFocus"
        @blur="onBlur"
        @keydown="onKeydown"
      />

      <!-- Right icon: loading / clear -->
      <div class="absolute right-2.5 top-1/2 -translate-y-1/2">
        <Loader2 v-if="isLoading" class="size-4 text-muted-foreground animate-spin" />
        <button
          v-else-if="isSelected && !disabled && !field.read_only"
          type="button"
          class="text-muted-foreground hover:text-foreground transition-colors"
          @mousedown.prevent="clear"
        >
          <X class="size-4" />
        </button>
      </div>
    </div>

    <!-- Dropdown -->
    <div
      v-if="isOpen"
      class="absolute top-full mt-1 left-0 right-0 bg-popover border border-border rounded-lg shadow-lg z-50 overflow-hidden"
    >
      <!-- Results -->
      <template v-if="results.length">
        <div class="max-h-52 overflow-y-auto py-1">
          <button
            v-for="(item, i) in results"
            :key="item.id"
            type="button"
            :class="[
              'w-full text-left px-3 py-2 text-sm transition-colors flex flex-col gap-0.5',
              i === activeIdx ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
            ]"
            @mousedown.prevent="select(item)"
            @mouseover="activeIdx = i"
          >
            <span v-html="highlight(getLabel(item))" />
            <span v-if="getSublabel(item)" class="text-xs text-muted-foreground" v-html="highlight(getSublabel(item)!)" />
          </button>
        </div>
      </template>

      <!-- States -->
      <div v-else class="px-3 py-3 text-sm text-muted-foreground text-center">
        <span v-if="isLoading">{{ t('Searching...') }}</span>
        <span v-else-if="query">{{ t('Nothing found for «{query}»', { query }) }}</span>
        <span v-else>{{ t('No records') }}</span>
      </div>
    </div>
  </div>
</template>
