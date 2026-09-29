<script setup lang="ts">
/**
 * Tree navigation beside a list (DocType.list_tree_field): the nodes of the
 * linked `is_tree` DocType — folders for File, departments for Employee…
 *
 * The open node *is* a list filter (`field = node`, `child_of` with nested,
 * `is not set` for «without»), so it lives in the URL like any other filter.
 * Dropping list rows on a node re-links them; dropping a node re-parents it.
 */
import { useI18n } from 'vue-i18n'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import {
  ChevronRight, Folder, FolderOpen, FolderPlus, FolderX, Layers, ListTree, MoreHorizontal,
} from '@lucide/vue'
import { docsApi, type TreeNode } from '@/core/api/docs'
import { useDocTypeStore } from '@/stores/doctype'
import { useAuthStore } from '@/stores/auth'
import { useDialog } from '@/core/composables/useDialog'
import { useToast } from '@/core/composables/useToast'
import { roleAllows } from '@/core/permissions'
import { docUrl } from '@/core/workspaceUrl'
import { ROW_DRAG_MIME, readDraggedRows } from '@/core/composables/useRowDrag'
import type { ActiveFilter, DocField, DocType } from '@/types'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const props = defineProps<{
  dt: DocType
  field: DocField
  filters: ActiveFilter[]
  workspace?: string
}>()
const emit = defineEmits<{
  'update:filters': [filters: ActiveFilter[]]
  /** Rows were re-linked — the list refetches. */
  moved: []
}>()

const { t } = useI18n()
const dtStore = useDocTypeStore()
const auth = useAuthStore()
const dialog = useDialog()
const toast = useToast()
const queryClient = useQueryClient()

const NODE_MIME = 'application/x-grunt-tree-node'
const ALL = '\u0000all'
const NONE = '\u0000none'
const TREE_OPS = ['=', 'child_of', 'is not set']

const treeDoctype = computed(() => props.field.options ?? '')
const treeDt = ref<DocType | null>(null)
const titleField = computed(() => treeDt.value?.tree_title_field || treeDt.value?.title_field || 'name')
const parentField = computed(() => treeDt.value?.tree_parent_field ?? '')
const roles = computed(() => auth.user?.roles ?? [])
const canCreate = computed(() => roleAllows(treeDt.value, 'create', roles.value))
const canMoveRows = computed(() => roleAllows(props.dt, 'write', roles.value))

// ── Nodes: loaded one level at a time ───────────────────────────────────────
const childrenOf = reactive(new Map<string, TreeNode[]>()) // '' → roots
const expanded = reactive(new Set<string>())
const titles = reactive(new Map<string, string>())

async function loadChildren(parent: string) {
  const nodes = await docsApi.getTreeChildren(treeDoctype.value, parent || null, {
    sort_by: treeDt.value?.tree_sort_by ?? undefined,
    sort_order: treeDt.value?.tree_sort_order ?? undefined,
  })
  for (const n of nodes) titles.set(n.name, nodeTitle(n))
  childrenOf.set(parent, nodes)
}

function nodeTitle(node: TreeNode): string {
  const value = node[titleField.value]
  return value === null || value === undefined || value === '' ? node.name : String(value)
}

async function reloadLoaded() {
  await Promise.all([...childrenOf.keys()].map(loadChildren))
}

async function toggle(node: TreeNode) {
  if (expanded.has(node.name)) {
    expanded.delete(node.name)
    return
  }
  if (!childrenOf.has(node.name)) await loadChildren(node.name)
  expanded.add(node.name)
}

interface Row { node: TreeNode; depth: number }
const rows = computed<Row[]>(() => {
  const out: Row[] = []
  const seen = new Set<string>() // a stale cache must never loop
  const walk = (parent: string, depth: number) => {
    for (const node of childrenOf.get(parent) ?? []) {
      if (seen.has(node.name)) continue
      seen.add(node.name)
      out.push({ node, depth })
      if (expanded.has(node.name)) walk(node.name, depth + 1)
    }
  }
  walk('', 0)
  return out
})

// ── Selection = the list filter on the field ────────────────────────────────
const current = computed(() =>
  props.filters.find((f) => f.fieldname === props.field.fieldname && TREE_OPS.includes(f.op)),
)
const selected = computed(() => {
  if (!current.value) return ALL
  return current.value.op === 'is not set' ? NONE : current.value.value
})
const includeNested = computed(() => current.value?.op === 'child_of')

function select(key: string, nested = includeNested.value) {
  const rest = props.filters.filter((f) => f !== current.value)
  const label = t(props.field.label ?? props.field.fieldname)
  if (key === ALL) {
    emit('update:filters', rest)
    return
  }
  const filter: ActiveFilter = key === NONE
    ? { fieldname: props.field.fieldname, label, fieldtype: 'Link', op: 'is not set', value: 'not set' }
    : {
        fieldname: props.field.fieldname,
        label,
        fieldtype: 'Link',
        op: nested ? 'child_of' : '=',
        value: key,
        displayValue: titles.get(key) ?? key,
      }
  emit('update:filters', [...rest, filter])
}

/** Opening the list on a node (from the URL) — unfold the path to it. */
async function revealSelected() {
  const key = selected.value
  if (key === ALL || key === NONE || titles.has(key) && isVisible(key)) return
  const path = await docsApi.getTreeAncestors(treeDoctype.value, key).catch(() => [])
  for (const node of path) {
    if (!childrenOf.has(node.name)) await loadChildren(node.name)
    expanded.add(node.name)
  }
}

function isVisible(name: string) {
  return rows.value.some((r) => r.node.name === name)
}

onMounted(async () => {
  treeDt.value = await dtStore.get(treeDoctype.value)
  await loadChildren('')
  await revealSelected()
})
watch(selected, revealSelected)

// ── Drag & drop ─────────────────────────────────────────────────────────────
const dropTarget = ref<string | null>(null)

function accepts(e: DragEvent): boolean {
  const types = e.dataTransfer?.types ?? []
  return (types.includes(ROW_DRAG_MIME) && canMoveRows.value) || types.includes(NODE_MIME)
}

function onDragOver(e: DragEvent, key: string) {
  if (!accepts(e)) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  dropTarget.value = key
}

function onNodeDragStart(e: DragEvent, node: TreeNode) {
  e.dataTransfer?.setData(NODE_MIME, node.name)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

async function onDrop(e: DragEvent, key: string) {
  dropTarget.value = null
  const target = key === NONE ? null : key
  const node = e.dataTransfer?.getData(NODE_MIME)
  try {
    if (node) {
      if (node === target) return
      await docsApi.moveTreeNode(treeDoctype.value, node, target)
      if (target) expanded.add(target)
      await reloadLoaded()
      if (target && !childrenOf.has(target)) await loadChildren(target)
      return
    }
    const dragged = readDraggedRows(e)
    if (!dragged || dragged.doctype !== props.dt.name || !dragged.ids.length) return
    const { updated, errors } = await docsApi.bulkUpdate(
      props.dt.name, dragged.ids, props.field.fieldname, target,
    )
    if (updated) {
      const n = String(updated)
      toast.success(
        t('Moved: {n}', { n }).replace('{n}', n) + (target ? ` → ${titles.get(target) ?? target}` : ''),
      )
      emit('moved')
    }
    // Rows the user may not change (e.g. someone else's file) come back as errors.
    if (errors.length) {
      const n = String(errors.length)
      toast.error(t('Not moved: {n}', { n }).replace('{n}', n) + ` — ${errors[0].replace(/^[^:]*:\s*/, '')}`)
    }
  } catch (err) {
    toast.error(errorText(err))
  }
}

// ── Node actions ────────────────────────────────────────────────────────────
async function createNode(parent: string | null) {
  const title = await dialog.prompt({ label: t('Name'), title: t('New folder'), required: true })
  if (!title?.trim()) return
  try {
    await docsApi.create(treeDoctype.value, {
      [titleField.value]: title.trim(),
      ...(parent ? { [parentField.value]: parent } : {}),
    })
    await loadChildren(parent ?? '')
    if (parent) expanded.add(parent)
    queryClient.invalidateQueries({ queryKey: ['documents', treeDoctype.value] })
  } catch (err) {
    toast.error(errorText(err))
  }
}

async function renameNode(node: TreeNode) {
  const title = await dialog.prompt({
    label: t('Name'), title: t('Rename'), required: true, default: nodeTitle(node),
  })
  if (!title?.trim() || title.trim() === nodeTitle(node)) return
  try {
    await docsApi.update(treeDoctype.value, node.name, { [titleField.value]: title.trim() })
    await reloadLoaded()
    if (selected.value === node.name) select(node.name) // refresh the chip label
    emit('moved')
  } catch (err) {
    toast.error(errorText(err))
  }
}

async function deleteNode(node: TreeNode) {
  const name = nodeTitle(node)
  if (!(await dialog.confirm(t('Delete «{name}»?', { name }).replace('{name}', name)))) return
  try {
    await docsApi.delete(treeDoctype.value, node.name)
    if (selected.value === node.name) select(ALL)
    await reloadLoaded()
  } catch (err) {
    toast.error(errorText(err))
  }
}

function errorText(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message)
  return t('Something went wrong')
}
</script>

<template>
  <nav class="flex flex-col gap-0.5 text-sm" :aria-label="t(field.label ?? field.fieldname)">
    <div class="mb-1 flex items-center gap-1 px-1">
      <span class="flex-1 truncate text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {{ t(field.label ?? field.fieldname) }}
      </span>
      <Button
        v-if="selected !== ALL && selected !== NONE"
        variant="ghost" size="icon" class="size-6"
        :class="includeNested && 'bg-accent text-accent-foreground'"
        :title="includeNested ? t('Only this level') : t('Include nested')"
        @click="select(selected, !includeNested)"
      >
        <Layers class="size-3.5" />
      </Button>
      <Button
        v-if="canCreate" variant="ghost" size="icon" class="size-6" :title="t('New folder')"
        @click="createNode(selected === ALL || selected === NONE ? null : selected)"
      >
        <FolderPlus class="size-3.5" />
      </Button>
    </div>

    <button
      type="button"
      class="flex items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-accent"
      :class="selected === ALL && 'bg-accent font-medium'"
      @click="select(ALL)"
    >
      <ListTree class="size-4 shrink-0 text-muted-foreground" />
      <span class="truncate">{{ t('All') }}</span>
    </button>
    <button
      type="button"
      class="flex items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-accent"
      :class="[selected === NONE && 'bg-accent font-medium', dropTarget === NONE && 'ring-2 ring-primary']"
      @click="select(NONE)"
      @dragover="onDragOver($event, NONE)"
      @dragleave="dropTarget = null"
      @drop="onDrop($event, NONE)"
    >
      <FolderX class="size-4 shrink-0 text-muted-foreground" />
      <span class="truncate">{{ t('Not set') }}</span>
    </button>

    <div
      v-for="{ node, depth } in rows"
      :key="node.name"
      class="group/node flex items-center rounded-md hover:bg-accent"
      :class="[selected === node.name && 'bg-accent font-medium', dropTarget === node.name && 'ring-2 ring-primary']"
      :style="{ paddingLeft: `${depth * 12}px` }"
      draggable="true"
      @dragstart="onNodeDragStart($event, node)"
      @dragover="onDragOver($event, node.name)"
      @dragleave="dropTarget = null"
      @drop="onDrop($event, node.name)"
    >
      <button
        type="button"
        class="flex size-6 shrink-0 items-center justify-center text-muted-foreground"
        :class="!node.has_children && 'invisible'"
        :aria-label="expanded.has(node.name) ? t('Collapse') : t('Expand')"
        @click="toggle(node)"
      >
        <ChevronRight class="size-3.5 transition-transform" :class="expanded.has(node.name) && 'rotate-90'" />
      </button>
      <button
        type="button"
        class="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-1 text-left"
        @click="select(node.name)"
        @dblclick="toggle(node)"
      >
        <component
          :is="selected === node.name || expanded.has(node.name) ? FolderOpen : Folder"
          class="size-4 shrink-0 text-muted-foreground"
        />
        <span class="truncate">{{ titles.get(node.name) ?? node.name }}</span>
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button
            variant="ghost" size="icon"
            class="size-6 shrink-0 opacity-0 group-hover/node:opacity-100 data-[state=open]:opacity-100"
            :aria-label="t('Actions')"
          >
            <MoreHorizontal class="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem v-if="canCreate" @click="createNode(node.name)">{{ t('New subfolder') }}</DropdownMenuItem>
          <DropdownMenuItem @click="renameNode(node)">{{ t('Rename') }}</DropdownMenuItem>
          <DropdownMenuItem as-child>
            <RouterLink :to="docUrl(treeDoctype, node.name, workspace)">{{ t('Open') }}</RouterLink>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem class="text-destructive" @click="deleteNode(node)">{{ t('Delete') }}</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  </nav>
</template>
