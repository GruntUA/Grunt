<script setup lang="ts">
import { ref, watch, computed, onUnmounted, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DocField } from '@/types'
import { docsApi, metaApi } from '@/core/api'
import type { LinkSearchItem } from '@/core/api/docs'
import { X, Loader2, ListTree } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { escapeHtml } from '@/lib/utils'
import { useAnchoredDropdown } from '@/core/composables/useAnchoredDropdown'
import TreePicker from './TreePicker.vue'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  /** Current document values - used to evaluate `link_filters` with an "eval:" prefix. */
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const { t } = useI18n()

// State
const query = ref('')
const results = ref<LinkSearchItem[]>([])
const isOpen = ref(false)
const isLoading = ref(false)
const activeIdx = ref(-1)

// name -> display label; seeded from search hits and resolved in bulk on load.
const labels = ref<Map<string, string>>(new Map())

// Tree target DocType -> values are picked in a dialog with the whole tree.
const isTree = ref(false)
const titleField = ref('name')
const pickerOpen = ref(false)

const inputEl = ref<HTMLInputElement | null>(null)
const anchorRef = ref<HTMLElement | null>(null)
const { dropdownStyle, reposition } = useAnchoredDropdown(isOpen, anchorRef)

const listboxId = useId()
const optionId = (i: number) => `${listboxId}-opt-${i}`

let debounceTimer: ReturnType<typeof setTimeout> | undefined
let blurTimer: ReturnType<typeof setTimeout> | undefined
let searchSeq = 0

// Derived
const readonly = computed(() => !!props.disabled || !!props.field.read_only)

const selectedValues = computed<string[]>(() => {
  const v = props.modelValue
  if (Array.isArray(v)) return v.map(String)
  if (typeof v === 'string' && v) {
    try {
      const parsed = JSON.parse(v)
      return Array.isArray(parsed) ? parsed.map(String) : []
    } catch {
      return []
    }
  }
  return []
})

// `link_filters`: raw JSON, or `eval:<expr>` evaluated against the parent doc.
const linkFilters = computed<Record<string, string | string[]>>(() => {
  const raw = props.field.link_filters
  if (!raw) return {}
  const trimmed = raw.trim()
  try {
    if (trimmed.startsWith('eval:')) {
      // eslint-disable-next-line no-new-func
      const r = new Function('doc', `return (${trimmed.slice(5).trim()})`)(props.doc ?? {})
      return r && typeof r === 'object' ? r : {}
    }
    return JSON.parse(raw)
  } catch {
    return {}
  }
})

const filteredResults = computed(() =>
  results.value.filter((r) => !selectedValues.value.includes(r.name)),
)

function labelFor(name: string): string {
  return labels.value.get(name) ?? name
}

// Label resolution (one request for every unresolved value)
async function resolveLabels(values: string[]) {
  const missing = values.filter((v) => !labels.value.has(v))
  if (!missing.length || !props.field.options) return
  const next = new Map(labels.value)
  try {
    const hits = await docsApi.linkSearch(props.field.options, '', { name__in: missing }, missing.length)
    hits.forEach((h) => next.set(h.name, h.title || h.name))
  } catch {
    /* fall through - unresolved names are shown as-is below */
  }
  missing.forEach((v) => { if (!next.has(v)) next.set(v, v) })
  labels.value = next
}

watch(
  () => props.field.options,
  async (doctype) => {
    labels.value = new Map()
    if (selectedValues.value.length) resolveLabels(selectedValues.value)
    isTree.value = false
    if (!doctype) return
    try {
      const meta = await metaApi.get(doctype)
      titleField.value = meta.title_field || 'name'
      isTree.value = !!meta.is_tree
    } catch {
      /* not readable as a tree - keep the plain search input */
    }
  },
  { immediate: true },
)
watch(selectedValues, (vals) => { if (vals.length) resolveLabels(vals) })

// Search
async function search(val: string) {
  if (!props.field.options) return
  const seq = ++searchSeq
  isLoading.value = true
  try {
    const hits = await docsApi.linkSearch(props.field.options, val, linkFilters.value, 20)
    if (seq !== searchSeq) return
    results.value = hits
    activeIdx.value = -1
    isOpen.value = true
  } catch {
    if (seq === searchSeq) results.value = []
  } finally {
    if (seq === searchSeq) isLoading.value = false
  }
}

function onInput(val: string) {
  query.value = val
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(val), val ? 300 : 0)
}

function onFocus() {
  clearTimeout(blurTimer)
  reposition()
  if (!isOpen.value) search(query.value)
}

function onBlur() {
  blurTimer = setTimeout(() => {
    isOpen.value = false
    query.value = ''
  }, 150)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Backspace' && !query.value && selectedValues.value.length) {
    e.preventDefault()
    removeValue(selectedValues.value[selectedValues.value.length - 1])
    return
  }
  if (!isOpen.value) return

  const items = filteredResults.value
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIdx.value = Math.min(activeIdx.value + 1, items.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIdx.value = Math.max(activeIdx.value - 1, -1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (items[activeIdx.value]) addItem(items[activeIdx.value])
  } else if (e.key === 'Escape') {
    e.preventDefault()
    isOpen.value = false
    query.value = ''
  }
}

// Selection
function addItem(item: LinkSearchItem) {
  if (selectedValues.value.includes(item.name)) return
  labels.value = new Map(labels.value).set(item.name, item.title || item.name)
  emit('update:modelValue', [...selectedValues.value, item.name])
  query.value = ''
  activeIdx.value = -1
  inputEl.value?.focus()
  search('') // refresh the list so the next pick is ready
}

function removeValue(name: string) {
  emit('update:modelValue', selectedValues.value.filter((v) => v !== name))
  inputEl.value?.focus()
}

function openPicker() {
  if (!readonly.value) pickerOpen.value = true
}

function onPicked(values: string[], picked: Map<string, string>) {
  labels.value = new Map([...labels.value, ...picked])
  emit('update:modelValue', values)
}

// Highlight (source text is user data -> always escaped before v-html)
function highlight(text: string): string {
  const safe = escapeHtml(text)
  const q = query.value.trim()
  if (!q) return safe
  const esc = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return safe.replace(
    new RegExp(`(${esc})`, 'gi'),
    '<mark class="bg-primary/20 text-foreground rounded-sm">$1</mark>',
  )
}

onUnmounted(() => {
  clearTimeout(debounceTimer)
  clearTimeout(blurTimer)
})
</script>

<template>
  <div class="relative">
    <!-- Tags + input -->
    <div
      ref="anchorRef"
      class="flex flex-wrap items-center gap-1 min-h-9 max-h-32 w-full overflow-y-auto rounded-md border border-input bg-transparent dark:bg-input/30 px-1.5 py-1 text-sm ring-offset-background transition-colors focus-within:outline-none focus-within:ring-2 focus-within:ring-ring focus-within:border-ring"
      :class="[
        error && 'border-destructive focus-within:ring-destructive',
        readonly && 'bg-muted/50 opacity-60 cursor-not-allowed',
      ]"
      @mousedown.self="isTree ? openPicker() : inputEl?.focus()"
    >
      <Badge
        v-for="val in selectedValues"
        :key="val"
        variant="secondary"
        class="rounded gap-1 pl-2 pr-1 py-0.5 font-normal max-w-[220px]"
      >
        <span class="min-w-0 truncate">{{ labelFor(val) }}</span>
        <button
          v-if="!readonly"
          type="button"
          class="shrink-0 rounded-sm text-muted-foreground transition-colors hover:bg-background/60 hover:text-foreground"
          :aria-label="t('Remove {item}', { item: labelFor(val) })"
          @mousedown.prevent="removeValue(val)"
        >
          <X class="size-3" />
        </button>
      </Badge>

      <button
        v-if="isTree && !readonly"
        type="button"
        class="flex min-w-[120px] flex-1 items-center gap-1.5 px-1 py-0.5 text-left text-muted-foreground outline-none hover:text-foreground focus-visible:text-foreground"
        :aria-label="t('Choose from the tree')"
        @click="openPicker"
      >
        <ListTree class="size-4 shrink-0" />
        <span>{{ selectedValues.length ? t('Change…') : (field.placeholder ?? t('Choose from the tree')) }}</span>
      </button>

      <input
        v-else-if="!readonly"
        ref="inputEl"
        :value="query"
        :placeholder="selectedValues.length ? '' : (field.placeholder ?? t('Search {doctype}…', { doctype: field.options ?? '' }))"
        class="min-w-[120px] flex-1 bg-transparent py-0.5 outline-none placeholder:text-muted-foreground"
        autocomplete="off"
        role="combobox"
        aria-autocomplete="list"
        :aria-label="field.label"
        :aria-expanded="isOpen"
        :aria-controls="listboxId"
        :aria-invalid="error ? true : undefined"
        :aria-activedescendant="isOpen && activeIdx >= 0 ? optionId(activeIdx) : undefined"
        @input="onInput(($event.target as HTMLInputElement).value)"
        @focus="onFocus"
        @blur="onBlur"
        @keydown="onKeydown"
      />

      <Loader2 v-if="isLoading" class="size-4 shrink-0 animate-spin text-muted-foreground" />
    </div>

    <TreePicker
      v-if="isTree && field.options"
      v-model:open="pickerOpen"
      :doctype="field.options"
      :title="field.label ?? ''"
      :title-field="titleField"
      :filters="linkFilters"
      :model-value="selectedValues"
      @update:model-value="onPicked"
    />

    <!-- Dropdown -->
    <Teleport to="body">
      <div
        v-if="isOpen && !readonly"
        :id="listboxId"
        role="listbox"
        :aria-label="field.label"
        :style="dropdownStyle"
        class="overflow-hidden rounded-lg border border-border bg-popover shadow-md"
      >
        <div v-if="filteredResults.length" class="max-h-52 overflow-y-auto py-1">
          <button
            v-for="(item, i) in filteredResults"
            :id="optionId(i)"
            :key="item.id"
            type="button"
            role="option"
            :aria-selected="i === activeIdx"
            :class="[
              'flex w-full flex-col gap-0.5 px-3 py-2 text-left text-sm transition-colors',
              i === activeIdx ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
            ]"
            @mousedown.prevent="addItem(item)"
            @mouseover="activeIdx = i"
          >
            <span v-html="highlight(item.title || item.name)" />
            <span
              v-if="item.fields?.length"
              class="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-muted-foreground"
            >
              <span v-for="f in item.fields" :key="f.fieldname">
                <span class="opacity-60">{{ f.label }}:</span>
                <span class="ml-1" v-html="highlight(f.value)" />
              </span>
            </span>
            <span
              v-else-if="item.subtitle && item.subtitle !== (item.title || item.name)"
              class="text-xs text-muted-foreground"
              v-html="highlight(item.subtitle)"
            />
          </button>
        </div>

        <div v-else class="px-3 py-3 text-center text-muted-foreground">
          <span v-if="isLoading">{{ t('Searching...') }}</span>
          <span v-else-if="query">{{ t('Nothing found for “{query}”', { query }) }}</span>
          <span v-else>{{ t('No records') }}</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>
