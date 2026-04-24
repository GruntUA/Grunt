<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { X, Loader2 } from '@lucide/vue'
import type { DocField } from '@/types'
import type { LinkSearchItem } from '@/core/api/docs'
import { docsApi, metaApi } from '@/core/api'
import TreeSelect from 'primevue/treeselect'
import type { TreeNode } from 'primevue/treenode'

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

const linkQuery = ref(props.displayValue || props.modelValue)
const linkResults = ref<LinkSearchItem[]>([])
const linkLoading = ref(false)
const _suppressClear = ref(false)

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
    if (isTree.value) {
      loadTree()
    }
  } catch {
    isTree.value = false
  }
}, { immediate: true })

function transformNodes(nodes: any[]): TreeNode[] {
  return nodes.map(node => ({
    key: node.id,
    label: node[titleField.value] || node.name || node.id,
    data: node,
    children: node.children?.length ? transformNodes(node.children) : undefined,
    leaf: !node.children?.length,
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

const treeSelection = computed<Record<string, boolean> | null>({
  get() {
    if (!props.modelValue) return null
    return { [props.modelValue]: true }
  },
  set(val) {
    if (!val || Object.keys(val).length === 0) {
      emit('update:modelValue', '')
      emit('update:displayValue', '')
    } else {
      const id = Object.keys(val)[0]
      emit('update:modelValue', id)
      // Resolve display label for filter tag
      const findTitle = (nodes: TreeNode[]): string | null => {
        for (const n of nodes) {
          if (n.key === id) return n.label ?? null
          if (n.children) {
            const found = findTitle(n.children)
            if (found) return found
          }
        }
        return null
      }
      const title = findTitle(treeNodes.value) || id
      emit('update:displayValue', title)
    }
  },
})

// Sync query when parent sets displayValue (e.g. when editing an existing filter)
watch(() => props.displayValue, (v) => {
  if (v && v !== linkQuery.value) {
    _suppressClear.value = true
    linkQuery.value = v
    setTimeout(() => { _suppressClear.value = false }, 0)
  }
})

let debounce: ReturnType<typeof setTimeout>
watch(linkQuery, (q) => {
  if (_suppressClear.value || isTree.value) return
  clearTimeout(debounce)
  emit('update:modelValue', '')
  emit('update:displayValue', '')
  if (!q.trim()) { linkResults.value = []; return }
  debounce = setTimeout(() => search(q), 280)
})

async function search(q: string) {
  const linkedDoctype = props.field.options
  if (!linkedDoctype || typeof linkedDoctype !== 'string') return
  linkLoading.value = true
  try {
    linkResults.value = await docsApi.linkSearch(linkedDoctype, q)
  } catch {
    linkResults.value = []
  } finally {
    linkLoading.value = false
  }
}

function selectItem(item: LinkSearchItem) {
  emit('update:modelValue', item.name)
  emit('update:displayValue', item.title || item.name)
  linkQuery.value = item.title || item.name
  linkResults.value = []
}

function clear() {
  emit('update:modelValue', '')
  emit('update:displayValue', '')
  linkQuery.value = ''
}
</script>

<template>
  <div class="mb-3 space-y-1.5">
    <!-- Tree mode -->
    <div v-if="isTree" class="relative">
      <TreeSelect
        v-model="treeSelection"
        :options="treeNodes"
        :loading="treeLoading"
        selection-mode="single"
        filter
        show-clear
        :placeholder="`Оберіть ${field.options}...`"
        class="w-full text-xs"
        @clear="clear"
      />
    </div>

    <!-- Regular mode -->
    <template v-else>
      <div class="relative">
        <InputText
          v-model="linkQuery"
          class="h-8 text-xs pr-7 w-full"
          :placeholder="`Пошук ${field.options}...`"
          @keydown.enter.prevent="linkResults[0] && selectItem(linkResults[0])"
        />
        <Loader2 v-if="linkLoading" class="absolute right-2 top-1/2 -translate-y-1/2 size-3.5 animate-spin text-muted-foreground" />
      </div>

      <div v-if="linkResults.length" class="border border-border rounded-md overflow-hidden max-h-40 overflow-y-auto divide-y divide-border/60">
        <button
          v-for="item in linkResults"
          :key="item.id"
          type="button"
          class="w-full px-3 py-2 text-left text-xs hover:bg-primary/5 transition-colors flex items-center gap-2"
          :class="modelValue === item.name ? 'bg-primary/10' : ''"
          @click="selectItem(item)"
        >
          <span class="font-medium text-foreground truncate flex-1">{{ item.title || item.name }}</span>
          <span v-if="item.subtitle" class="text-muted-foreground/60 shrink-0 truncate max-w-[80px]">{{ item.subtitle }}</span>
        </button>
      </div>
      <p v-else-if="linkQuery && !linkLoading && !modelValue" class="text-xs text-muted-foreground/60 italic px-1">
        Нічого не знайдено
      </p>

      <div v-if="modelValue" class="flex items-center gap-1.5 px-2 py-1 bg-primary/5 border border-primary/20 rounded-md text-xs text-primary">
        <span class="truncate flex-1">{{ displayValue || modelValue }}</span>
        <button type="button" class="shrink-0 hover:text-destructive" @click="clear">
          <X class="size-3" />
        </button>
      </div>
    </template>
  </div>
</template>
