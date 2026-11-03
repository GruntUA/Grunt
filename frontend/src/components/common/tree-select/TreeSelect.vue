<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, watch, nextTick, useId } from 'vue'
import { X, Pencil, Search } from '@lucide/vue'
import { cn } from '@/lib/utils'
import { Spinner } from '@/components/ui/spinner'
import { Kbd } from '@/components/ui/kbd'
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

const { t } = useI18n()

const props = withDefaults(defineProps<{
  modelValue: string | null
  options: TreeNode[]
  loading?: boolean
  placeholder?: string
  disabled?: boolean
  class?: string
}>(), {
  placeholder: undefined,
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

function clearDialogSearch() {
  search.value = ''
  emit('filter', '')
  dialogSearchEl.value?.focus()
}

/** Visible tree rows of the dialog, in document (= visual) order. */
function dialogRows(): HTMLElement[] {
  return Array.from(dialogListEl.value?.querySelectorAll<HTMLElement>('[data-tree-row]') ?? [])
}

function focusRow(row: HTMLElement | undefined) {
  if (!row) return
  row.focus()
  row.scrollIntoView({ block: 'nearest' })
}

/** Row of the parent node: row → wrapper → role="group" → parent's row. */
function parentRow(row: HTMLElement): HTMLElement | undefined {
  const group = row.parentElement?.parentElement
  if (group?.getAttribute('role') !== 'group') return undefined
  return (group.previousElementSibling as HTMLElement | null) ?? undefined
}

function onDialogSearchKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    focusRow(dialogRows()[0])
  } else if (e.key === 'Enter') {
    // Enter in the search box picks the first match.
    e.preventDefault()
    const key = dialogRows()[0]?.dataset.key
    if (key) onSelect(key)
  }
}

/** WAI-ARIA tree keyboard model: ↑↓ move, → expand/descend, ← collapse/ascend, ↵ pick. */
function onDialogListKeydown(e: KeyboardEvent) {
  const rows = dialogRows()
  const row = document.activeElement as HTMLElement | null
  const i = row ? rows.indexOf(row) : -1
  if (i < 0 || !row) return
  const key = row.dataset.key!
  const expandedAttr = row.getAttribute('aria-expanded')
  switch (e.key) {
    case 'ArrowDown':
      focusRow(rows[i + 1])
      break
    case 'ArrowUp':
      if (i === 0) dialogSearchEl.value?.focus()
      else focusRow(rows[i - 1])
      break
    case 'Home':
      focusRow(rows[0])
      break
    case 'End':
      focusRow(rows.at(-1))
      break
    case 'ArrowRight':
      if (expandedAttr === 'false') onToggle(key)
      else if (expandedAttr === 'true') focusRow(rows[i + 1])
      break
    case 'ArrowLeft':
      if (expandedAttr === 'true') onToggle(key)
      else focusRow(parentRow(row))
      break
    case 'Enter':
    case ' ':
      onSelect(key)
      break
    default:
      // Typing anywhere in the tree continues the search.
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) dialogSearchEl.value?.focus()
      return
  }
  e.preventDefault()
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
          :placeholder="placeholder ?? t('— Select —')"
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
            :aria-label="t('Choose from list')"
            @click.stop="openDialog"
            @mousedown.stop.prevent
          >
            <Pencil class="size-3.5" />
          </button>
          <button
            v-if="selectedLabel && !disabled"
            type="button"
            class="text-muted-foreground/70 transition-colors hover:text-foreground"
            :aria-label="t('Clear')"
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
          :query="search"
          @select="onSelect"
          @toggle="onToggle"
        />
        <p v-if="!filteredOptions.length" class="px-2 py-3 text-center text-muted-foreground">{{ t('Nothing found') }}</p>
      </div>
    </PopoverContent>
  </Popover>

  <Dialog v-model:open="dialogOpen">
    <DialogContent class="gap-0 overflow-hidden p-0 sm:max-w-xl" @open-auto-focus.prevent>
      <DialogHeader class="px-4 pt-4 pb-3 pr-10">
        <DialogTitle>{{ placeholder ?? t('— Select —') }}</DialogTitle>
        <DialogDescription>{{ t('Choose a value from the tree') }}</DialogDescription>
      </DialogHeader>
      <div class="flex h-10 items-center gap-2 border-y px-3">
        <Search class="size-4 shrink-0 opacity-50" />
        <input
          ref="dialogSearchEl"
          :value="search"
          :placeholder="t('Search…')"
          autocomplete="off"
          class="h-full w-full bg-transparent text-sm outline-hidden placeholder:text-muted-foreground"
          @input="onDialogSearch"
          @keydown="onDialogSearchKeydown"
        >
        <button
          v-if="search"
          type="button"
          class="shrink-0 text-muted-foreground hover:text-foreground"
          :aria-label="t('Clear search')"
          @click="clearDialogSearch"
        >
          <X class="size-4" />
        </button>
      </div>
      <div
        ref="dialogListEl"
        role="tree"
        :aria-label="placeholder"
        class="h-[min(60vh,28rem)] overflow-y-auto p-1"
        @keydown="onDialogListKeydown"
      >
        <TreeSelectNode
          v-for="node in filteredOptions"
          :key="node.key"
          :node="node"
          :depth="0"
          :selected-key="modelValue"
          :expanded-keys="expandedKeys"
          :query="search"
          @select="onSelect"
          @toggle="onToggle"
        />
        <p v-if="!filteredOptions.length" class="py-10 text-center text-sm text-muted-foreground">{{ t('Nothing found') }}</p>
      </div>
      <div class="hidden items-center gap-4 border-t px-4 py-2 text-xs text-muted-foreground sm:flex">
        <span class="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd>{{ t('Navigate') }}</span>
        <span class="flex items-center gap-1"><Kbd>←</Kbd><Kbd>→</Kbd>{{ t('Expand') }}</span>
        <span class="flex items-center gap-1"><Kbd>↵</Kbd>{{ t('Select') }}</span>
        <span class="ml-auto flex items-center gap-1"><Kbd>Esc</Kbd>{{ t('Close') }}</span>
      </div>
    </DialogContent>
  </Dialog>
</template>
