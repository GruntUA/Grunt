<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ChevronDown, X, Search } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Spinner } from '@/components/ui/spinner'
import TreeSelectNode from './TreeSelectNode.vue'
import type { TreeNode } from './types'

const props = withDefaults(defineProps<{
  modelValue: string | null
  options: TreeNode[]
  loading?: boolean
  placeholder?: string
  disabled?: boolean
  class?: string
}>(), {
  placeholder: '— оберіть —',
})

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  filter: [query: string]
}>()

const isOpen = ref(false)
const anchorEl = ref<HTMLElement | null>(null)
const search = ref('')
const expandedKeys = ref<Record<string, boolean>>({})

function toggle(event: Event) {
  if (props.disabled) return
  if (isOpen.value) { isOpen.value = false; return }
  anchorEl.value = event.currentTarget as HTMLElement
  search.value = ''
  isOpen.value = true
}

function findNode(nodes: TreeNode[], key: string): TreeNode | null {
  for (const n of nodes) {
    if (n.key === key) return n
    if (n.children) {
      const found = findNode(n.children, key)
      if (found) return found
    }
  }
  return null
}

const selectedLabel = computed(() => {
  if (!props.modelValue) return null
  return findNode(props.options, props.modelValue)?.label ?? props.modelValue
})

/** Expand ancestors leading to `key`; returns true once `key` is found in this subtree. */
function expandPathTo(nodes: TreeNode[], key: string): boolean {
  for (const n of nodes) {
    if (n.key === key) return true
    if (n.children?.length && expandPathTo(n.children, key)) {
      expandedKeys.value[n.key] = true
      return true
    }
  }
  return false
}

function getAllKeys(nodes: TreeNode[], acc: Record<string, boolean> = {}): Record<string, boolean> {
  for (const n of nodes) {
    acc[n.key] = true
    if (n.children?.length) getAllKeys(n.children, acc)
  }
  return acc
}

function matches(node: TreeNode, q: string): boolean {
  if (node.label.toLowerCase().includes(q)) return true
  return !!node.children?.some(c => matches(c, q))
}

function filterNodes(nodes: TreeNode[], q: string): TreeNode[] {
  const result: TreeNode[] = []
  for (const n of nodes) {
    if (matches(n, q)) {
      result.push(n.children?.length ? { ...n, children: filterNodes(n.children, q) } : n)
    }
  }
  return result
}

const filteredOptions = computed<TreeNode[]>(() => {
  const q = search.value.trim().toLowerCase()
  return q ? filterNodes(props.options, q) : props.options
})

watch(search, (q) => {
  if (q.trim()) expandedKeys.value = getAllKeys(filteredOptions.value)
})

watch([() => props.modelValue, () => props.options], ([key]) => {
  if (key) expandPathTo(props.options, key)
}, { immediate: true })

function onSelect(key: string) {
  emit('update:modelValue', key)
  isOpen.value = false
}

function onToggle(key: string) {
  expandedKeys.value[key] = !expandedKeys.value[key]
}

function onClear(e: Event) {
  e.stopPropagation()
  emit('update:modelValue', null)
}
</script>

<template>
  <button
    type="button"
    :disabled="disabled"
    :class="cn(
      'border-input flex h-9 w-full items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] hover:bg-accent/50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3 disabled:cursor-not-allowed disabled:opacity-50',
      !selectedLabel && 'text-muted-foreground',
      props.class,
    )"
    @click="toggle"
  >
    <span class="truncate">{{ selectedLabel || placeholder }}</span>
    <span class="flex items-center gap-1 shrink-0">
      <X v-if="selectedLabel" class="size-3.5 opacity-50 hover:opacity-100" @click.stop="onClear" />
      <Spinner v-if="loading" class="size-4" />
      <ChevronDown v-else class="size-4 opacity-50" />
    </span>
  </button>

  <Popover v-model:open="isOpen">
    <PopoverAnchor :reference="anchorEl ?? undefined" />
    <PopoverContent class="w-(--reka-popper-anchor-width) min-w-56 p-0">
      <div class="flex items-center gap-1.5 p-1.5 border-b border-border">
        <Search class="size-3.5 text-muted-foreground shrink-0 ml-1" />
        <input
          v-model="search"
          autofocus
          placeholder="Пошук..."
          class="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground px-1 py-1"
          @input="emit('filter', search)"
        >
      </div>
      <div class="max-h-64 overflow-y-auto p-1">
        <TreeSelectNode
          v-for="node in filteredOptions"
          :key="node.key"
          :node="node"
          :depth="0"
          :selected-key="modelValue"
          :expanded-keys="expandedKeys"
          @select="onSelect"
          @toggle="onToggle"
        />
        <p v-if="!filteredOptions.length" class="px-2 py-3 text-center text-sm text-muted-foreground">Нічого не знайдено</p>
      </div>
    </PopoverContent>
  </Popover>
</template>
