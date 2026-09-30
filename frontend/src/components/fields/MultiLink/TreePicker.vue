<script setup lang="ts">
/** Multi-select picker for a tree DocType: a large dialog with search and checkboxes. */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search, X } from '@lucide/vue'
import { docsApi } from '@/core/api'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { TreeSelectNode, type TreeNode } from '@/components/ui/tree-select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const props = defineProps<{
  doctype: string
  title: string
  titleField: string
  filters: Record<string, string | string[]>
  modelValue: string[]
}>()

const emit = defineEmits<{
  /** Confirmed selection, with the labels of the picked nodes. */
  'update:modelValue': [value: string[], labels: Map<string, string>]
}>()

const open = defineModel<boolean>('open', { required: true })

const { t } = useI18n()

const nodes = ref<TreeNode[]>([])
const loading = ref(false)
const search = ref('')
const picked = ref<string[]>([])
const expandedKeys = ref<Record<string, boolean>>({})

interface RawTreeNode {
  id: string
  name?: string
  display_title?: string
  children?: RawTreeNode[]
  [key: string]: unknown
}

function transform(raw: RawTreeNode[]): TreeNode[] {
  return raw.map((n) => ({
    key: n.id,
    label: n.display_title || (n[props.titleField] as string | undefined) || n.name || n.id,
    children: n.children?.length ? transform(n.children) : undefined,
  }))
}

async function load() {
  loading.value = true
  try {
    // Tree filters are plain equality — list-valued link filters don't apply here.
    const quickFilters: Record<string, string> = {}
    for (const [k, v] of Object.entries(props.filters)) if (typeof v === 'string') quickFilters[k] = v
    nodes.value = transform(await docsApi.getTree(props.doctype, { quickFilters }))
  } catch {
    nodes.value = []
  } finally {
    loading.value = false
  }
}

function matches(node: TreeNode, q: string): boolean {
  return node.label.toLowerCase().includes(q) || !!node.children?.some((c) => matches(c, q))
}

function filterNodes(list: TreeNode[], q: string): TreeNode[] {
  return list
    .filter((n) => matches(n, q))
    .map((n) => (n.children?.length ? { ...n, children: filterNodes(n.children, q) } : n))
}

const visibleNodes = computed(() => {
  const q = search.value.trim().toLowerCase()
  return q ? filterNodes(nodes.value, q) : nodes.value
})

function walk(list: TreeNode[], visit: (n: TreeNode, ancestors: TreeNode[]) => void, ancestors: TreeNode[] = []) {
  for (const n of list) {
    visit(n, ancestors)
    if (n.children?.length) walk(n.children, visit, [...ancestors, n])
  }
}

/** Roots open, plus the path to every picked node. */
function expandInitial() {
  const expanded: Record<string, boolean> = {}
  nodes.value.forEach((n) => { expanded[n.key] = true })
  walk(nodes.value, (n, ancestors) => {
    if (picked.value.includes(n.key)) ancestors.forEach((a) => { expanded[a.key] = true })
  })
  expandedKeys.value = expanded
}

watch(open, async (isOpen) => {
  if (!isOpen) return
  search.value = ''
  picked.value = [...props.modelValue]
  await load()
  expandInitial()
})

watch(search, (q) => {
  if (!q.trim()) return
  const expanded: Record<string, boolean> = {}
  walk(visibleNodes.value, (n) => { expanded[n.key] = true })
  expandedKeys.value = expanded
})

function onSelect(key: string) {
  picked.value = picked.value.includes(key)
    ? picked.value.filter((k) => k !== key)
    : [...picked.value, key]
}

function onToggle(key: string) {
  expandedKeys.value[key] = !expandedKeys.value[key]
}

function confirm() {
  const labels = new Map<string, string>()
  walk(nodes.value, (n) => { if (picked.value.includes(n.key)) labels.set(n.key, n.label) })
  emit('update:modelValue', picked.value, labels)
  open.value = false
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="gap-0 overflow-hidden p-0 sm:max-w-3xl">
      <DialogHeader class="px-4 pt-4 pb-3 pr-10">
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>{{ t('Tick the items you need in the tree') }}</DialogDescription>
      </DialogHeader>
      <div class="flex h-10 items-center gap-2 border-y px-3">
        <Search class="size-4 shrink-0 opacity-50" />
        <input
          v-model="search"
          :placeholder="t('Search…')"
          autocomplete="off"
          class="h-full w-full bg-transparent text-sm outline-hidden placeholder:text-muted-foreground"
        >
        <button
          v-if="search"
          type="button"
          class="shrink-0 text-muted-foreground hover:text-foreground"
          :aria-label="t('Clear search')"
          @click="search = ''"
        >
          <X class="size-4" />
        </button>
      </div>
      <div role="tree" aria-multiselectable="true" :aria-label="title" class="h-[min(70vh,40rem)] overflow-y-auto p-1">
        <div v-if="loading" class="flex justify-center py-10"><Spinner class="size-5" /></div>
        <template v-else>
          <TreeSelectNode
            v-for="node in visibleNodes"
            :key="node.key"
            :node="node"
            :depth="0"
            :selected-key="null"
            :selected-keys="picked"
            :expanded-keys="expandedKeys"
            :query="search"
            @select="onSelect"
            @toggle="onToggle"
          />
          <p v-if="!visibleNodes.length" class="py-10 text-center text-sm text-muted-foreground">{{ t('Nothing found') }}</p>
        </template>
      </div>
      <DialogFooter class="items-center border-t px-4 py-3 sm:justify-between">
        <span class="text-muted-foreground">{{ t('Selected: {n}', { n: picked.length }) }}</span>
        <div class="flex gap-2">
          <Button v-if="picked.length" variant="ghost" @click="picked = []">{{ t('Clear') }}</Button>
          <Button variant="outline" @click="open = false">{{ t('Cancel') }}</Button>
          <Button @click="confirm">{{ t('Done') }}</Button>
        </div>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
