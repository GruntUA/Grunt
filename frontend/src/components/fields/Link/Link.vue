<script setup lang="ts">
import { ref, watch, computed, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { DocField } from '@/types'
import { docsApi, metaApi } from '@/core/api'
import type { LinkSearchItem } from '@/core/api/docs'
import { Search, X, Loader2, Plus, ArrowUpRight } from 'lucide-vue-next'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  /** Current document values — used to evaluate link_filters with "eval:" prefix. */
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  'create-new': [doctype: string, preset: string]
}>()

// ── State ─────────────────────────────────────────────────────────────────────

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const query = ref('')
const results = ref<LinkSearchItem[]>([])
const isOpen = ref(false)
const isLoading = ref(false)
const activeIdx = ref(-1)
const titleField = ref<string>('name')

// Cache: name → display label
const displayCache = new Map<string, string>()

let debounceTimer: ReturnType<typeof setTimeout>
let blurTimer: ReturnType<typeof setTimeout>

// ── Script-registered filters (from frm.set_query) ───────────────────────────

type LinkFiltersFn = (fieldname: string, doc: Record<string, unknown>) => Record<string, string>
const getScriptFilters = inject<LinkFiltersFn>('getLinkFilters', () => ({}))

// ── Resolve link_filters ──────────────────────────────────────────────────────

/**
 * Evaluate the field's link_filters against the current document.
 *
 *  '{"status": "Active"}'         → parsed as JSON
 *  'eval: {"company": doc.company}' → evaluated as JS with doc in scope
 */
function resolveFilters(): Record<string, string> {
  const doc = props.doc ?? {}

  // 1. Script-registered filters via frm.set_query (highest priority)
  const scriptFilters = getScriptFilters(props.field.fieldname, doc)

  // 2. Static/eval filters from field.link_filters metadata
  let metaFilters: Record<string, string> = {}
  const raw = props.field.link_filters
  if (raw) {
    try {
      if (raw.trim().startsWith('eval:')) {
        const expr = raw.trim().slice(5).trim()
        // eslint-disable-next-line no-new-func
        const result = new Function('doc', `return (${expr})`)(doc)
        metaFilters = typeof result === 'object' && result ? result : {}
      } else {
        metaFilters = JSON.parse(raw)
      }
    } catch { /* ignore */ }
  }

  // Script filters override meta filters for the same key
  return { ...metaFilters, ...scriptFilters }
}

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
  query.value = raw
  query.value = await resolveDisplay(raw)
}

// ── Sync value → display ──────────────────────────────────────────────────────

watch(() => props.modelValue, (v) => { syncQueryFromValue(v) })

watch(() => props.field.options, async (doctype) => {
  if (!doctype) return
  try {
    const meta = await metaApi.get(doctype)
    titleField.value = meta.title_field || 'name'
  } catch {
    titleField.value = 'name'
  }
  if (props.modelValue) syncQueryFromValue(props.modelValue)
}, { immediate: true })

// ── Search via dedicated link_search endpoint ─────────────────────────────────

async function search(val: string) {
  if (!props.field.options) return
  isLoading.value = true
  try {
    results.value = await docsApi.linkSearch(
      props.field.options,
      val,
      resolveFilters(),
    )
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
    syncQueryFromValue(props.modelValue)
  }, 200)
}

// ── Keyboard navigation ───────────────────────────────────────────────────────

// Total navigable items = results + optional "create" button
const totalItems = computed(() => results.value.length + (canCreate.value ? 1 : 0))

function onKeydown(e: KeyboardEvent) {
  if (!isOpen.value) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIdx.value = Math.min(activeIdx.value + 1, totalItems.value - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIdx.value = Math.max(activeIdx.value - 1, -1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (activeIdx.value === results.value.length && canCreate.value) {
      // Last item — "Create" button
      createNew()
    } else if (activeIdx.value >= 0 && results.value[activeIdx.value]) {
      select(results.value[activeIdx.value])
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    isOpen.value = false
    syncQueryFromValue(props.modelValue)
  }
}

// ── Selection ─────────────────────────────────────────────────────────────────

function select(item: LinkSearchItem) {
  displayCache.set(item.name, item.title)
  query.value = item.title
  emit('update:modelValue', item.name)
  isOpen.value = false
}

function clear() {
  query.value = ''
  emit('update:modelValue', null)
  isOpen.value = false
}

// ── Create new ────────────────────────────────────────────────────────────────

/**
 * Show the "Create" button when the user has typed something and no exact
 * match exists, or when there are no results at all.
 */
const canCreate = computed(() =>
  !!(props.field.options && !props.disabled && !props.field.read_only)
)

/**
 * Navigate to the new-document form for the linked DocType.
 * Emits "create-new" for parent forms to intercept (e.g. open a dialog).
 * Falls back to router navigation so it works standalone.
 */
function createNew() {
  if (!props.field.options) return
  isOpen.value = false
  emit('create-new', props.field.options, query.value)
  // Default fallback: open new-doc page (workspace route)
  // Parent components can prevent this by catching the event.
}

// ── Highlight ─────────────────────────────────────────────────────────────────

function highlight(text: string): string {
  if (!query.value.trim()) return text
  const escaped = query.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(
    new RegExp(`(${escaped})`, 'gi'),
    '<mark class="bg-primary/20 text-foreground rounded-sm">$1</mark>',
  )
}

const isSelected = computed(
  () => props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== '',
)

// URL to the linked document's form page
const linkedDocUrl = computed(() => {
  if (!isSelected.value || !props.field.options || !props.modelValue) return null
  const workspace = route.params.workspaceName as string | undefined
  if (workspace) return `/${workspace}/list/${props.field.options}/${props.modelValue}`
  return null
})

function openLinkedDoc() {
  if (linkedDocUrl.value) router.push(linkedDocUrl.value)
}
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
        :class="[
          'w-full rounded-md border border-input bg-transparent pl-8 py-2 text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-ring disabled:bg-muted disabled:cursor-not-allowed transition-colors',
          isSelected && linkedDocUrl ? 'pr-16' : 'pr-8',
          error ? 'border-destructive focus-visible:ring-destructive' : '',
        ]"
        autocomplete="off"
        @input="onInput(($event.target as HTMLInputElement).value)"
        @focus="onFocus"
        @blur="onBlur"
        @keydown="onKeydown"
      />

      <!-- Right icons: loading / open link / clear -->
      <div class="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center gap-1">
        <Loader2 v-if="isLoading" class="size-4 text-muted-foreground animate-spin" />
        <template v-else-if="isSelected">
          <button
            v-if="linkedDocUrl"
            type="button"
            class="text-muted-foreground hover:text-primary transition-colors"
            :title="t('Open {doctype}', { doctype: field.options ?? '' })"
            @mousedown.prevent="openLinkedDoc"
          >
            <ArrowUpRight class="size-4" />
          </button>
          <button
            v-if="!disabled && !field.read_only"
            type="button"
            class="text-muted-foreground hover:text-foreground transition-colors"
            @mousedown.prevent="clear"
          >
            <X class="size-4" />
          </button>
        </template>
      </div>
    </div>

    <!-- Dropdown -->
    <div
      v-if="isOpen"
      class="absolute top-full mt-1 left-0 right-0 bg-popover border border-border rounded-lg shadow-lg z-50 overflow-hidden"
    >
      <!-- Results -->
      <div v-if="results.length" class="max-h-52 overflow-y-auto py-1">
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
          <span v-html="highlight(item.title)" />
          <span
            v-if="item.subtitle"
            class="text-xs text-muted-foreground"
            v-html="highlight(item.subtitle)"
          />
        </button>
      </div>

      <!-- Empty state -->
      <div v-else class="px-3 py-3 text-sm text-muted-foreground text-center">
        <span v-if="isLoading">{{ t('Searching...') }}</span>
        <span v-else-if="query">{{ t('Nothing found for «{query}»', { query }) }}</span>
        <span v-else>{{ t('No records') }}</span>
      </div>

      <!-- Create new button (always at the bottom when field.options is set) -->
      <template v-if="canCreate">
        <div class="border-t border-border" />
        <button
          type="button"
          :class="[
            'w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors',
            activeIdx === results.length
              ? 'bg-accent text-accent-foreground'
              : 'text-primary hover:bg-accent/50',
          ]"
          @mousedown.prevent="createNew"
          @mouseover="activeIdx = results.length"
        >
          <Plus class="size-3.5 shrink-0" />
          <span v-if="query">
            {{ t('Create') }} <strong>{{ query }}</strong>
            <span class="text-muted-foreground text-xs ml-1">({{ field.options }})</span>
          </span>
          <span v-else class="text-muted-foreground">
            {{ t('Create new') }} {{ field.options }}
          </span>
        </button>
      </template>
    </div>
  </div>
</template>
