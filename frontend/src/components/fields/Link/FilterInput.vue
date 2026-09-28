<script setup lang="ts">
import { computed, ref, watch, onUnmounted, useId } from 'vue'
import { X, Loader2 } from '@lucide/vue'
import type { DocField } from '@/types'
import type { LinkSearchItem } from '@/core/api/docs'
import { docsApi, metaApi } from '@/core/api'
import { MULTI_VALUE_OPS } from '@/core/api/docs'
import type { TreeNode } from '@/components/ui/tree-select'
import { Input } from '@/components/ui/input'
import { TreeSelect } from '@/components/ui/tree-select'
import { escapeHtml } from '@/lib/utils'
import { useAnchoredDropdown } from '@/core/composables/useAnchoredDropdown'

const props = defineProps<{
  field: DocField
  modelValue: string
  displayValue: string
  op: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:displayValue': [value: string]
  'submit': []
}>()

// `in` / `not in`: modelValue is a CSV of ids, shown as removable chips.
const multi = computed(() => MULTI_VALUE_OPS.includes(props.op))
const values = computed(() => props.modelValue ? props.modelValue.split(',') : [])
const titles = ref<Record<string, string>>({})

const query = ref(multi.value ? '' : props.displayValue || props.modelValue)
watch(multi, (m) => { query.value = m ? '' : props.displayValue || props.modelValue })
const results = ref<LinkSearchItem[]>([])
const isLoading = ref(false)
const isOpen = ref(false)
const activeIdx = ref(-1)

const anchorRef = ref<HTMLElement | null>(null)
const { dropdownStyle, reposition } = useAnchoredDropdown(isOpen, anchorRef)
const listboxId = useId()
const optionId = (i: number) => `${listboxId}-opt-${i}`

// Tree mode
const isTree = ref(false)
const treeNodes = ref<TreeNode[]>([])
const treeLoading = ref(false)
const titleField = ref('name')

let debounceTimer: ReturnType<typeof setTimeout>
let blurTimer: ReturnType<typeof setTimeout>
let searchSeq = 0

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

// Sync query when parent sets displayValue from outside (e.g. applying a saved preset)
watch(() => props.displayValue, (v) => {
  if (v && v !== query.value) query.value = v
})

async function search(val: string) {
  const linkedDoctype = props.field.options
  if (!linkedDoctype || typeof linkedDoctype !== 'string') return
  const seq = ++searchSeq
  isLoading.value = true
  try {
    const hits = await docsApi.linkSearch(linkedDoctype, val)
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

function setValues(ids: string[]) {
  emit('update:modelValue', ids.join(','))
  emit('update:displayValue', ids.map(id => titles.value[id] ?? id).join(', '))
}

function onInput(val: string) {
  query.value = val
  if (isTree.value && !multi.value) return
  if (!multi.value) {
    emit('update:modelValue', '')
    emit('update:displayValue', '')
  }
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(val), val ? 300 : 0)
}

function onFocus() {
  clearTimeout(blurTimer)
  reposition()
  if (!isOpen.value) search(query.value)
}

function onBlur() {
  blurTimer = setTimeout(() => { isOpen.value = false }, 150)
}

function selectItem(item: LinkSearchItem) {
  if (multi.value) {
    titles.value[item.name] = item.title || item.name
    if (!values.value.includes(item.name)) setValues([...values.value, item.name])
    query.value = ''
    return
  }
  emit('update:modelValue', item.name)
  emit('update:displayValue', item.title || item.name)
  query.value = item.title || item.name
  isOpen.value = false
}

function clear() {
  emit('update:modelValue', '')
  emit('update:displayValue', '')
  query.value = ''
  results.value = []
}

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
    const item = results.value[activeIdx.value] ?? results.value[0]
    if (item) selectItem(item)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    isOpen.value = false
  }
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

onUnmounted(() => {
  clearTimeout(debounceTimer)
  clearTimeout(blurTimer)
})
</script>

<template>
  <!-- Tree mode -->
  <TreeSelect
    v-if="isTree && !multi"
    :model-value="modelValue || null"
    :options="treeNodes"
    :loading="treeLoading"
    :placeholder="`Оберіть ${field.options}...`"
    class="w-full text-xs"
    @update:model-value="onTreeSelect"
  />

  <!-- Regular mode -->
  <div v-else ref="anchorRef" class="relative">
    <div v-if="multi && values.length" class="flex flex-wrap gap-1 mb-1">
      <span
        v-for="id in values" :key="id"
        class="inline-flex items-center gap-1 rounded-md border bg-muted px-1.5 py-0.5 max-w-full"
      >
        <span class="truncate">{{ titles[id] ?? id }}</span>
        <button
          type="button" class="text-muted-foreground hover:text-foreground" aria-label="Прибрати"
          @mousedown.prevent="setValues(values.filter(v => v !== id))"
        >
          <X class="size-3" />
        </button>
      </span>
    </div>
    <Input
      :model-value="query"
      class="h-8 text-xs w-full pr-7"
      :placeholder="`Пошук ${field.options}...`"
      autocomplete="off"
      role="combobox"
      aria-autocomplete="list"
      :aria-expanded="isOpen"
      :aria-controls="listboxId"
      :aria-activedescendant="isOpen && activeIdx >= 0 ? optionId(activeIdx) : undefined"
      @update:model-value="onInput(String($event))"
      @focus="onFocus"
      @blur="onBlur"
      @keydown="onKeydown"
    />
    <Loader2 v-if="isLoading" class="absolute right-2 top-1/2 -translate-y-1/2 size-3.5 animate-spin text-muted-foreground" />
    <button
      v-else-if="modelValue && !multi"
      type="button"
      class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
      aria-label="Очистити"
      @mousedown.prevent="clear"
    >
      <X class="size-3.5" />
    </button>

    <Teleport to="body">
      <div
        v-if="isOpen"
        :id="listboxId"
        data-link-dropdown
        role="listbox"
        :style="dropdownStyle"
        class="overflow-hidden rounded-lg border border-border bg-popover text-xs shadow-md"
      >
        <div v-if="results.length" class="max-h-52 overflow-y-auto py-1">
          <button
            v-for="(item, i) in results"
            :id="optionId(i)"
            :key="item.id"
            type="button"
            role="option"
            :aria-selected="i === activeIdx"
            :class="[
              'flex w-full flex-col gap-0.5 px-3 py-1.5 text-left transition-colors',
              i === activeIdx || values.includes(item.name) ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
            ]"
            @mousedown.prevent="selectItem(item)"
            @mouseover="activeIdx = i"
          >
            <span class="truncate font-medium" v-html="highlight(item.title || item.name)" />
            <span v-if="item.subtitle" class="truncate text-muted-foreground/70" v-html="highlight(item.subtitle)" />
          </button>
        </div>
        <div v-else class="px-3 py-3 text-center text-muted-foreground">
          <span v-if="isLoading">Пошук...</span>
          <span v-else-if="query">Нічого не знайдено</span>
          <span v-else>Немає записів</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>
