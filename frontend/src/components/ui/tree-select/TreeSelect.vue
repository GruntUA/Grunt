<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ChevronDown, X, Search } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Spinner } from '@/components/ui/spinner'
import TreeSelectNode from './TreeSelectNode.vue'
import type { TreeNode } from './types'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'

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
const triggerEl = ref<HTMLElement | null>(null)
const search = ref('')
const expandedKeys = ref<Record<string, boolean>>({})

function openTree() {
  anchorEl.value = triggerEl.value
  search.value = ''
  isOpen.value = true
}

/**
 * The trigger is a plain focusable element (not a <button>) so the selected
 * label stays selectable — the user can drag over it to copy the value.
 * A click that ends such a drag must not also open the tree.
 */
function selectionInsideTrigger(): boolean {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || !sel.toString().trim()) return false
  return !!(sel.anchorNode && triggerEl.value?.contains(sel.anchorNode))
}

function onTriggerClick() {
  if (props.disabled || selectionInsideTrigger()) return
  if (isOpen.value) { isOpen.value = false; return }
  openTree()
}

function onTriggerKeydown(e: KeyboardEvent) {
  if (props.disabled) return
  if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
    e.preventDefault()
    if (!isOpen.value) openTree()
  } else if (e.key === 'Escape' && isOpen.value) {
    isOpen.value = false
  }
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
  <div
    ref="triggerEl"
    role="button"
    aria-haspopup="tree"
    :aria-expanded="isOpen"
    :aria-disabled="disabled || undefined"
    :tabindex="disabled ? undefined : 0"
    :class="cn(
      'border-input text-foreground dark:bg-input/30 dark:hover:bg-input/50 flex h-9 w-full items-center justify-between gap-2 rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] hover:bg-accent/50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3',
      disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
      !selectedLabel && 'text-muted-foreground',
      props.class,
    )"
    @click="onTriggerClick"
    @keydown="onTriggerKeydown"
  >
    <span class="truncate" :class="selectedLabel && 'cursor-text select-text'">{{ selectedLabel || placeholder }}</span>
    <span class="flex items-center gap-1 shrink-0">
      <button
        v-if="selectedLabel && !disabled"
        type="button"
        class="text-muted-foreground/70 transition-colors hover:text-foreground"
        aria-label="Очистити"
        @click.stop="onClear"
        @mousedown.stop
      >
        <X class="size-3.5" />
      </button>
      <Spinner v-if="loading" class="size-4" />
      <ChevronDown v-else class="size-4 opacity-50 pointer-events-none" />
    </span>
  </div>

  <Popover v-model:open="isOpen">
    <PopoverAnchor :reference="anchorEl ?? undefined" />
    <PopoverContent class="w-(--reka-popper-anchor-width) min-w-56 p-0">
      <div class="flex items-center gap-1.5 p-1.5 border-b border-border">
        <Search class="size-3.5 text-muted-foreground shrink-0 ml-1" />
        <input
          v-model="search"
          autofocus
          placeholder="Пошук..."
          class="w-full bg-transparent outline-none placeholder:text-muted-foreground px-1 py-1"
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
        <p v-if="!filteredOptions.length" class="px-2 py-3 text-center text-muted-foreground">Нічого не знайдено</p>
      </div>
    </PopoverContent>
  </Popover>
</template>
