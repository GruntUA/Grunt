<script setup lang="ts">
import { ref, computed, watch, nextTick, useId } from 'vue'
import { X, Pencil } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Spinner } from '@/components/ui/spinner'
import TreeSelectNode from './TreeSelectNode.vue'
import type { TreeNode } from './types'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

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

const listboxId = useId()
const isOpen = ref(false)
const dialogOpen = ref(false)
const triggerEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLInputElement | null>(null)
const contentEl = ref<HTMLElement | null>(null)
const dialogListEl = ref<HTMLElement | null>(null)
const dialogSearchEl = ref<HTMLInputElement | null>(null)
/** Live text typed into the field; also the tree filter query. */
const search = ref('')
const expandedKeys = ref<Record<string, boolean>>({})
let blurTimer: ReturnType<typeof setTimeout> | undefined

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

/**
 * While the dropdown is open the field shows what the user is typing; when
 * closed it shows the picked label. Focusing an already-picked field starts a
 * fresh search (empty) so the full tree is offered, mirroring the Link input.
 */
const displayValue = computed(() => (isOpen.value ? search.value : (selectedLabel.value ?? '')))

function open() {
  if (props.disabled) return
  if (!isOpen.value) {
    search.value = ''
    isOpen.value = true
  }
}

function onFocus() {
  clearTimeout(blurTimer)
  open()
}

function onInput(e: Event) {
  search.value = (e.target as HTMLInputElement).value
  emit('filter', search.value)
  open()
}

function onBlur() {
  blurTimer = setTimeout(() => {
    // Stay open while focus is inside the dropdown (e.g. an expander button).
    if (contentEl.value?.contains(document.activeElement)) return
    isOpen.value = false
  }, 120)
}

function onInputKeydown(e: KeyboardEvent) {
  if (props.disabled) return
  if (e.key === 'Escape' && isOpen.value) {
    e.preventDefault()
    isOpen.value = false
    inputEl.value?.blur()
  } else if ((e.key === 'ArrowDown' || e.key === 'Enter') && !isOpen.value) {
    e.preventDefault()
    open()
  }
}

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

watch(isOpen, (openNow) => {
  if (!openNow) search.value = ''
})

watch(dialogOpen, async (openNow) => {
  if (!openNow) { search.value = ''; return }
  // Opening the picker: start clean and reveal the current selection.
  search.value = ''
  isOpen.value = false
  if (props.modelValue) expandPathTo(props.options, props.modelValue)
  await nextTick()
  // Land focus on the currently selected node (scrolled into view), so the
  // picker opens right where the user left off; fall back to the search box.
  const selectedRow = dialogListEl.value?.querySelector<HTMLElement>('[data-selected]')
  if (selectedRow) {
    selectedRow.scrollIntoView({ block: 'center' })
    selectedRow.focus()
  } else {
    dialogSearchEl.value?.focus()
  }
})

function onSelect(key: string) {
  emit('update:modelValue', key)
  clearTimeout(blurTimer)
  isOpen.value = false
  dialogOpen.value = false
  inputEl.value?.blur()
}

function onToggle(key: string) {
  expandedKeys.value[key] = !expandedKeys.value[key]
  // Clicking an expander in the inline dropdown steals focus from the input —
  // hand it straight back so the user can keep typing.
  if (!dialogOpen.value) inputEl.value?.focus()
}

function onClear(e: Event) {
  e.stopPropagation()
  emit('update:modelValue', null)
  emit('filter', '')
  search.value = ''
  inputEl.value?.focus()
}

function openDialog() {
  if (props.disabled) return
  dialogOpen.value = true
}

function onDialogSearch(e: Event) {
  search.value = (e.target as HTMLInputElement).value
  emit('filter', search.value)
}

/** Keep the popover open when the "outside" interaction is the field itself. */
function keepOpenIfSelf(e: CustomEvent<{ originalEvent?: Event }>) {
  const target = (e.detail?.originalEvent?.target ?? e.target) as Node | null
  if (target && triggerEl.value?.contains(target)) e.preventDefault()
}
</script>

<template>
  <Popover v-model:open="isOpen">
    <PopoverAnchor as-child>
      <div ref="triggerEl" class="relative w-full min-w-0">
        <input
          ref="inputEl"
          :value="displayValue"
          :placeholder="placeholder"
          :disabled="disabled"
          role="combobox"
          aria-haspopup="tree"
          aria-autocomplete="list"
          :aria-expanded="isOpen"
          :aria-controls="listboxId"
          autocomplete="off"
          :class="cn(
            'border-input text-foreground dark:bg-input/30 flex h-9 w-full rounded-md border bg-transparent py-2 pl-3 pr-20 text-sm shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3 disabled:cursor-not-allowed disabled:opacity-60',
            props.class,
          )"
          @focus="onFocus"
          @input="onInput"
          @blur="onBlur"
          @keydown="onInputKeydown"
        >
        <div class="absolute right-2.5 top-1/2 flex -translate-y-1/2 items-center gap-1">
          <slot name="actions" />
          <button
            v-if="!disabled"
            type="button"
            class="text-muted-foreground/70 transition-colors hover:text-foreground"
            aria-label="Обрати зі списку"
            @click.stop="openDialog"
            @mousedown.stop.prevent
          >
            <Pencil class="size-3.5" />
          </button>
          <button
            v-if="selectedLabel && !disabled"
            type="button"
            class="text-muted-foreground/70 transition-colors hover:text-foreground"
            aria-label="Очистити"
            @click.stop="onClear"
            @mousedown.stop.prevent
          >
            <X class="size-3.5" />
          </button>
          <Spinner v-if="loading" class="size-4" />
        </div>
      </div>
    </PopoverAnchor>

    <PopoverContent
      :id="listboxId"
      align="start"
      class="w-(--reka-popper-anchor-width) min-w-56 p-0"
      @open-auto-focus.prevent
      @close-auto-focus.prevent
      @pointer-down-outside="keepOpenIfSelf"
      @focus-outside="keepOpenIfSelf"
    >
      <div ref="contentEl" class="max-h-64 overflow-y-auto p-1">
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

  <Dialog v-model:open="dialogOpen">
    <DialogContent class="gap-0 p-0 sm:max-w-6xl" @open-auto-focus.prevent>
      <DialogHeader class="border-b border-border px-4 py-3 pr-10">
        <DialogTitle>{{ placeholder }}</DialogTitle>
        <DialogDescription class="sr-only">Оберіть значення з дерева</DialogDescription>
      </DialogHeader>
      <div class="border-b border-border px-3 py-2">
        <input
          ref="dialogSearchEl"
          :value="search"
          placeholder="Пошук…"
          autocomplete="off"
          class="w-full bg-transparent py-1 text-sm outline-none placeholder:text-muted-foreground"
          @input="onDialogSearch"
        >
      </div>
      <div ref="dialogListEl" class="max-h-[60vh] min-h-40 overflow-y-auto p-2">
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
        <p v-if="!filteredOptions.length" class="px-2 py-6 text-center text-muted-foreground">Нічого не знайдено</p>
      </div>
    </DialogContent>
  </Dialog>
</template>
