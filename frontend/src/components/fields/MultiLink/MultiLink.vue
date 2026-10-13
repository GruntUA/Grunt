<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ComboboxInput } from 'reka-ui'
import type { DocField } from '@/types'
import { docsApi, metaApi } from '@/core/api'
import type { LinkSearchItem } from '@/core/api/docs'
import { ListTree } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Combobox, ComboboxAnchor, ComboboxGroup, ComboboxItem, ComboboxList } from '@/components/ui/combobox'
import { Spinner } from '@/components/ui/spinner'
import {
  TagsInput, TagsInputInput, TagsInputItem, TagsInputItemDelete, TagsInputItemText,
} from '@/components/ui/tags-input'
import { escapeHtml } from '@/lib/utils'
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

// name -> display label; seeded from search hits and resolved in bulk on load.
const labels = ref<Map<string, string>>(new Map())

// Tree target DocType -> values are picked in a dialog with the whole tree.
const isTree = ref(false)
const titleField = ref('name')
const pickerOpen = ref(false)

let debounceTimer: ReturnType<typeof setTimeout> | undefined
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
  } catch {
    if (seq === searchSeq) results.value = []
  } finally {
    if (seq === searchSeq) isLoading.value = false
  }
}

function onInput(val: string) {
  if (val === query.value) return
  query.value = val
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(val), val ? 300 : 0)
}

function onOpenChange(open: boolean) {
  isOpen.value = open
  if (open) search(query.value)
  else query.value = ''
}

// Selection. The list stays open (the item's select is prevented), so
// several records can be picked in a row.
function addItem(event: Event, item: LinkSearchItem) {
  event.preventDefault()
  if (selectedValues.value.includes(item.name)) return
  labels.value = new Map(labels.value).set(item.name, item.title || item.name)
  emit('update:modelValue', [...selectedValues.value, item.name])
  query.value = ''
  search('') // refresh the list so the next pick is ready
}

// TagsInput reports removals (× or Backspace); it would also turn typed text
// into a tag, which is never a valid record name - only removals are kept.
function onTagsChange(values: unknown[]) {
  const kept = values.map(String).filter((v) => selectedValues.value.includes(v))
  if (kept.length !== selectedValues.value.length) emit('update:modelValue', kept)
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

onUnmounted(() => clearTimeout(debounceTimer))
</script>

<template>
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

  <!-- Tree DocType: values are picked in the tree dialog -->
  <TagsInput
    v-if="isTree"
    :model-value="selectedValues"
    :display-value="(v) => labelFor(String(v))"
    :disabled="readonly"
    :aria-invalid="error ? true : undefined"
    class="max-h-32 overflow-y-auto data-[disabled]:opacity-60"
    @update:model-value="onTagsChange"
  >
    <TagsInputItem v-for="val in selectedValues" :key="val" :value="val" class="max-w-[220px]">
      <TagsInputItemText class="truncate" />
      <TagsInputItemDelete v-if="!readonly" :aria-label="t('Remove {item}', { item: labelFor(val) })" />
    </TagsInputItem>
    <Button
      v-if="!readonly"
      type="button"
      variant="ghost"
      size="xs"
      class="text-muted-foreground"
      :aria-label="t('Choose from the tree')"
      @click="openPicker"
    >
      <ListTree />
      {{ selectedValues.length ? t('Change…') : (field.placeholder ?? t('Choose from the tree')) }}
    </Button>
  </TagsInput>

  <!-- Flat DocType: type to search on the server; picking adds a tag -->
  <Combobox
    v-else
    :open="isOpen"
    :disabled="readonly"
    ignore-filter
    open-on-focus
    open-on-click
    :reset-search-term-on-blur="false"
    :reset-search-term-on-select="false"
    @update:open="onOpenChange"
  >
    <ComboboxAnchor as-child class="w-full">
      <TagsInput
        :model-value="selectedValues"
        :display-value="(v) => labelFor(String(v))"
        :disabled="readonly"
        :aria-invalid="error ? true : undefined"
        class="max-h-32 overflow-y-auto data-[disabled]:opacity-60"
        @update:model-value="onTagsChange"
      >
        <TagsInputItem v-for="val in selectedValues" :key="val" :value="val" class="max-w-[220px]">
          <TagsInputItemText class="truncate" />
          <TagsInputItemDelete v-if="!readonly" :aria-label="t('Remove {item}', { item: labelFor(val) })" />
        </TagsInputItem>
        <ComboboxInput as-child :model-value="query" :display-value="() => query" @update:model-value="onInput">
          <TagsInputInput
            :placeholder="selectedValues.length ? '' : (field.placeholder ?? t('Search {doctype}…', { doctype: field.options ?? '' }))"
            :aria-label="field.label"
            autocomplete="off"
            class="min-w-[120px]"
            @keydown.enter.prevent
          />
        </ComboboxInput>
        <Spinner v-if="isLoading" class="text-muted-foreground" />
      </TagsInput>
    </ComboboxAnchor>

    <ComboboxList
      class="w-(--reka-popper-anchor-width) min-w-56 p-0"
      align="start"
      data-link-dropdown
      @open-auto-focus.prevent
    >
      <ComboboxGroup v-if="filteredResults.length" class="max-h-52 overflow-y-auto p-1">
        <ComboboxItem v-for="item in filteredResults" :key="item.id" :value="item.name" @select="addItem($event, item)">
          <div class="flex min-w-0 flex-col gap-0.5">
            <span v-html="highlight(item.title || item.name)" />
            <span v-if="item.fields?.length" class="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
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
          </div>
        </ComboboxItem>
      </ComboboxGroup>
      <div v-else class="py-6 text-center text-sm text-muted-foreground">
        <span v-if="isLoading">{{ t('Searching...') }}</span>
        <span v-else-if="query">{{ t('Nothing found for “{query}”', { query }) }}</span>
        <span v-else>{{ t('No records') }}</span>
      </div>
    </ComboboxList>
  </Combobox>
</template>
