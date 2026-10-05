<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch, onUnmounted } from 'vue'
import { Check, ChevronsUpDown, X } from '@lucide/vue'
import type { AcceptableValue } from 'reka-ui'
import type { DocField } from '@/types'
import type { LinkSearchItem } from '@/core/api/docs'
import { docsApi, metaApi } from '@/core/api'
import { MULTI_VALUE_OPS } from '@/core/api/docs'
import type { TreeNode } from '@/components/ui/tree-select'
import { TreeSelect } from '@/components/ui/tree-select'
import {
  Combobox, ComboboxAnchor, ComboboxGroup, ComboboxInput, ComboboxItem,
  ComboboxItemIndicator, ComboboxList, ComboboxTrigger,
} from '@/components/ui/combobox'
import { InputGroup, InputGroupAddon, InputGroupButton } from '@/components/ui/input-group'
import { Spinner } from '@/components/ui/spinner'
import { escapeHtml } from '@/lib/utils'

const { t } = useI18n()

const props = defineProps<{
  field: DocField
  modelValue: string
  displayValue: string
  op: string
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:displayValue': [value: string]
  'submit': []
}>()

// `in` / `not in`: modelValue is a CSV of ids and the combobox picks several.
const multi = computed(() => MULTI_VALUE_OPS.includes(props.op))
const values = computed(() => props.modelValue ? props.modelValue.split(',') : [])

// Titles of the picked ids; seeded from displayValue ("A, B") when it arrives from outside.
const titles = ref<Record<string, string>>({})
watch(() => [props.modelValue, props.displayValue] as const, ([ids, display]) => {
  if (!ids || !display) return
  const idList = ids.split(',')
  const titleList = idList.length === 1 ? [display] : display.split(', ')
  if (titleList.length !== idList.length) return
  idList.forEach((id, i) => { titles.value[id] ??= titleList[i] })
}, { immediate: true })

const triggerLabel = computed(() => values.value.map(id => titles.value[id] ?? id).join(', '))

const query = ref('')
const results = ref<LinkSearchItem[]>([])
const isLoading = ref(false)
const isOpen = ref(false)

// Tree mode
const isTree = ref(false)
const treeNodes = ref<TreeNode[]>([])
const treeLoading = ref(false)
const titleField = ref('name')

watch(() => props.field.options, async (doctype) => {
  if (!doctype) return
  try {
    const meta = await metaApi.get(doctype)
    isTree.value = !!meta.is_tree
    titleField.value = meta.title_field || 'name'
    if (isTree.value) loadTree()
  } catch {
    isTree.value = false
  }
}, { immediate: true })

function transformNodes(nodes: any[]): TreeNode[] {
  return nodes.map(node => ({
    key: node.id,
    label: node[titleField.value] || node.name || node.id,
    children: node.children?.length ? transformNodes(node.children) : undefined,
  }))
}

async function loadTree() {
  if (!props.field.options) return
  treeLoading.value = true
  try {
    const raw = await docsApi.getTree(props.field.options)
    treeNodes.value = transformNodes(raw)
  } catch {
    treeNodes.value = []
  } finally {
    treeLoading.value = false
  }
}

function onTreeSelect(id: string | null) {
  if (!id) {
    emit('update:modelValue', '')
    emit('update:displayValue', '')
    return
  }
  emit('update:modelValue', id)
  function findTitle(nodes: TreeNode[]): string | null {
    for (const n of nodes) {
      if (n.key === id) return n.label ?? null
      if (n.children) {
        const found = findTitle(n.children)
        if (found) return found
      }
    }
    return null
  }
  emit('update:displayValue', findTitle(treeNodes.value) || id)
}

// Search
let debounceTimer: ReturnType<typeof setTimeout>
let searchSeq = 0

async function search(val: string) {
  const linkedDoctype = props.field.options
  if (!linkedDoctype || typeof linkedDoctype !== 'string') return
  const seq = ++searchSeq
  isLoading.value = true
  try {
    const hits = await docsApi.linkSearch(linkedDoctype, val)
    if (seq === searchSeq) results.value = hits
  } catch {
    if (seq === searchSeq) results.value = []
  } finally {
    if (seq === searchSeq) isLoading.value = false
  }
}

watch(query, (val) => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(val), val ? 300 : 0)
})

watch(isOpen, (open) => { if (open) search(query.value) })

// Selection
function rememberTitles(ids: string[]) {
  for (const id of ids) {
    const hit = results.value.find(r => r.name === id)
    if (hit) titles.value[id] = hit.title || hit.name
  }
}

function onPick(v: AcceptableValue | AcceptableValue[]) {
  const ids = (Array.isArray(v) ? v : v == null ? [] : [v]).map(String)
  rememberTitles(ids)
  emit('update:modelValue', ids.join(','))
  emit('update:displayValue', ids.map(id => titles.value[id] ?? id).join(', '))
}

function clear() {
  emit('update:modelValue', '')
  emit('update:displayValue', '')
  query.value = ''
}

function highlight(text: string): string {
  const safe = escapeHtml(text ?? '')
  if (!query.value.trim()) return safe
  const esc = query.value.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return safe.replace(
    new RegExp(`(${esc})`, 'gi'),
    '<mark class="bg-primary/20 text-foreground rounded-sm">$1</mark>',
  )
}

onUnmounted(() => clearTimeout(debounceTimer))
</script>

<template>
  <!-- Tree mode -->
  <TreeSelect
    v-if="isTree && !multi"
    :model-value="modelValue || null"
    :options="treeNodes"
    :loading="treeLoading"
    :placeholder="placeholder ?? t('Select {doctype}…', { doctype: field.options ?? '' })"
    class="w-full"
    @update:model-value="onTreeSelect"
  />

  <!-- Regular mode: server-side search, so the combobox doesn't filter by itself -->
  <Combobox
    v-else
    v-model:open="isOpen"
    :model-value="multi ? values : (modelValue || undefined)"
    :multiple="multi"
    ignore-filter
    @update:model-value="onPick"
  >
    <ComboboxAnchor as-child>
      <InputGroup class="w-full">
        <ComboboxTrigger as-child>
          <button
            type="button"
            data-slot="input-group-control"
            class="flex h-full min-w-0 flex-1 items-center rounded-md px-3 text-left text-sm outline-none"
            :class="!values.length && 'text-muted-foreground'"
          >
            <span class="truncate">{{ triggerLabel || placeholder || t('Select {doctype}…', { doctype: field.options ?? '' }) }}</span>
          </button>
        </ComboboxTrigger>
        <InputGroupAddon align="inline-end">
          <InputGroupButton
            v-if="values.length"
            size="icon-xs"
            :aria-label="t('Clear')"
            :title="t('Clear')"
            @click="clear"
          >
            <X />
          </InputGroupButton>
          <ChevronsUpDown v-else class="opacity-50" />
        </InputGroupAddon>
      </InputGroup>
    </ComboboxAnchor>

    <ComboboxList class="w-(--reka-popper-anchor-width) min-w-56" align="start" data-link-dropdown>
      <ComboboxInput
        v-model="query"
        :display-value="() => ''"
        :placeholder="t('Search {doctype}…', { doctype: field.options ?? '' })"
      />
      <div v-if="!results.length" class="flex items-center justify-center gap-2 py-6 text-center text-sm text-muted-foreground">
        <template v-if="isLoading"><Spinner /> {{ t('Searching...') }}</template>
        <template v-else-if="query">{{ t('Nothing found') }}</template>
        <template v-else>{{ t('No records') }}</template>
      </div>
      <ComboboxGroup v-else class="max-h-60 overflow-y-auto">
        <ComboboxItem v-for="item in results" :key="item.id" :value="item.name">
          <div class="flex min-w-0 flex-col gap-0.5">
            <span class="truncate" v-html="highlight(item.title || item.name)" />
            <span v-if="item.subtitle" class="truncate text-xs text-muted-foreground" v-html="highlight(item.subtitle)" />
          </div>
          <ComboboxItemIndicator><Check /></ComboboxItemIndicator>
        </ComboboxItem>
      </ComboboxGroup>
    </ComboboxList>
  </Combobox>
</template>
