<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { docsApi } from '@/core/api/docs'
import {
  ChevronRight, ChevronDown, Plus, FolderOpen,
  AlertCircle, RefreshCw
} from '@lucide/vue'
import type { DocType, GruntDocument } from '@/types'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'

const props = defineProps<{
  doctype: DocType
  parentField: string
  workspace?: string
}>()

const { t } = useI18n()
const router = useRouter()

// ── State ────────────────────────────────────────────────────────────────

const allDocs = ref<GruntDocument[]>([])
const loading = ref(false)
const error = ref('')

// ── Persist expanded ids to localStorage ─────────────────────────────────

const STORAGE_KEY = `tree_expanded_${props.doctype.name}`

function loadExpandedIds(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return new Set(JSON.parse(raw) as string[])
  } catch { /* ignore */ }
  return new Set()
}

function saveExpandedIds(ids: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]))
  } catch { /* ignore */ }
}

const expandedIds = ref<Set<string>>(loadExpandedIds())

// ── Data fetching ────────────────────────────────────────────────────────

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    // Load all records — tree structures are typically small enough
    const result = await docsApi.list(props.doctype.name, { per_page: 500 })
    allDocs.value = result.data
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : t('Load error')
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)

// ── Tree building ────────────────────────────────────────────────────────

const titleField = computed(() =>
  props.doctype.tree_view?.title_field
    ?? props.doctype.title_field
    ?? props.doctype.fields.find(f => f.fieldtype === 'Text' && f.in_list_view)?.fieldname
    ?? 'name'
)

function getTitle(doc: GruntDocument): string {
  const v = doc[titleField.value]
  if (v !== null && v !== undefined) return String(v)
  return doc.name ?? String(doc.id)
}

function getParentId(doc: GruntDocument): string | null {
  const v = doc[props.parentField]
  return v !== null && v !== undefined && v !== '' ? String(v) : null
}

const tree = computed<TreeNode[]>(() => {
  const byId = new Map<string, TreeNode>()
  const byName = new Map<string, TreeNode>()
  const roots: TreeNode[] = []

  // First pass: create all nodes and index by ID and Name
  for (const doc of allDocs.value) {
    const node: TreeNode = {
      id: String(doc.id),
      data: doc,
      children: [],
      expanded: expandedIds.value.has(String(doc.id)),
    }
    byId.set(node.id, node)
    if (doc.name) {
      byName.set(String(doc.name), node)
    }
  }

  // Second pass: attach children
  for (const doc of allDocs.value) {
    const node = byId.get(String(doc.id))!
    const parentIdOrName = getParentId(doc)
    
    const parentNode = parentIdOrName 
      ? (byId.get(parentIdOrName) || byName.get(parentIdOrName))
      : null

    if (parentNode && parentNode !== node) {
      parentNode.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return roots
})

// ── Interactions ─────────────────────────────────────────────────────────

function toggle(node: TreeNode) {
  if (expandedIds.value.has(node.id)) {
    expandedIds.value.delete(node.id)
  } else {
    expandedIds.value.add(node.id)
  }
  // Trigger reactivity
  expandedIds.value = new Set(expandedIds.value)
  saveExpandedIds(expandedIds.value)
}

function expandAll(nodes: TreeNode[] = tree.value) {
  for (const n of nodes) {
    if (n.children.length > 0) {
      expandedIds.value.add(n.id)
      expandAll(n.children)
    }
  }
  expandedIds.value = new Set(expandedIds.value)
  saveExpandedIds(expandedIds.value)
}

function collapseAll() {
  expandedIds.value = new Set()
  saveExpandedIds(expandedIds.value)
}

function navigateTo(node: TreeNode) {
  const id = node.id
  if (props.workspace) {
    router.push(`/${props.workspace}/${props.doctype.name}/${id}`)
  } else {
    router.push(`/${props.doctype.name}/${id}`)
  }
}

// ── Quick entry for child creation ─────────────────────────────────────────

const quickEntryPreset = ref<Record<string, unknown> | null>(null)

function createChild(parentNode: TreeNode) {
  quickEntryPreset.value = { [props.parentField]: parentNode.id }
}

function onQuickEntrySaved() {
  quickEntryPreset.value = null
  loadAll()
}

function createRoot() {
  if (props.workspace) {
    router.push(`/${props.workspace}/${props.doctype.name}/new`)
  } else {
    router.push(`/${props.doctype.name}/new`)
  }
}

// ── Stats ────────────────────────────────────────────────────────────────

function countDescendants(node: TreeNode): number {
  let count = node.children.length
  for (const child of node.children) count += countDescendants(child)
  return count
}

interface TreeNode {
  id: string
  data: GruntDocument
  children: TreeNode[]
  expanded: boolean
}
</script>

<template>
  <div>
    <!-- Toolbar -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <Button text size="small" @click="expandAll()">
          <ChevronDown class="size-3.5 mr-1" />
          Розгорнути все
        </Button>
        <Button text size="small" @click="collapseAll">
          <ChevronRight class="size-3.5 mr-1" />
          Згорнути все
        </Button>
      </div>
      <div class="flex items-center gap-2">
        <Button text :title="t('Refresh')" @click="loadAll">
          <RefreshCw class="size-4" :class="{ 'animate-spin': loading }" />
        </Button>
        <Button size="small" @click="createRoot">
          <Plus class="size-4 mr-1.5" />
          Новий кореневий
        </Button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading && !allDocs.length" class="flex justify-center py-16">
      <ProgressSpinner class="size-10!" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex items-center gap-3 p-4 rounded-lg bg-destructive/10 text-destructive text-sm">
      <AlertCircle class="size-4 shrink-0" />
      {{ error }}
      <Button text size="small" class="ml-auto" @click="loadAll">{{ t('Retry') }}</Button>
    </div>

    <!-- Empty -->
    <div v-else-if="!loading && !allDocs.length" class="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
      <FolderOpen class="size-12 opacity-30" />
      <p class="text-sm">Записів поки немає</p>
      <Button size="small" @click="createRoot">
        <Plus class="size-4 mr-1.5" />
        Створити перший
      </Button>
    </div>

    <!-- Tree -->
    <div v-else class="border border-border rounded-lg overflow-hidden bg-card shadow-sm">
      <TreeNodeRow
        v-for="node in tree"
        :key="node.id"
        :node="node"
        :depth="0"
        :expanded-ids="expandedIds"
        :get-title="getTitle"
        :count-descendants="countDescendants"
        @toggle="toggle"
        @navigate="navigateTo"
        @create-child="createChild"
      />
    </div>

    <!-- Counter -->
    <p v-if="allDocs.length" class="mt-3 text-xs text-muted-foreground text-right">
      Всього: {{ allDocs.length }} записів
    </p>

    <!-- Quick entry dialog for child creation -->
    <QuickEntryDialog
      v-if="quickEntryPreset !== null"
      :dt="doctype"
      :preset="quickEntryPreset"
      :workspace="workspace"
      mode="list"
      @close="quickEntryPreset = null"
      @saved="onQuickEntrySaved"
    />
  </div>
</template>

<!-- ── Recursive tree node ──────────────────────────────────────────────── -->
<script lang="ts">
import { defineComponent, h, type PropType } from 'vue'
import { ChevronRight as CR, ChevronDown as CD, Plus as PL, Folder as FL, FolderOpen as FO, FileText as FT } from '@lucide/vue'

interface TreeNode {
  id: string
  data: Record<string, unknown>
  children: TreeNode[]
  expanded: boolean
}

const TreeNodeRow: any = defineComponent({
  name: 'TreeNodeRow',
  props: {
    node: { type: Object as PropType<TreeNode>, required: true },
    depth: { type: Number, required: true },
    expandedIds: { type: Object as PropType<Set<string>>, required: true },
    getTitle: { type: Function as PropType<(doc: any) => string>, required: true },
    countDescendants: { type: Function as PropType<(node: any) => number>, required: true },
  },
  emits: ['toggle', 'navigate', 'create-child'],
  setup(props, { emit }) {
    return () => {
      const { node, depth, expandedIds } = props
      const isExpanded = expandedIds.has(node.id)
      const hasChildren = node.children.length > 0
      const indent = depth * 20 // px per level

      const chevron = hasChildren
        ? h(isExpanded ? CD : CR, {
            class: 'size-4 text-muted-foreground shrink-0 transition-transform duration-150',
            onClick: (e: Event) => { e.stopPropagation(); emit('toggle', node) },
          })
        : h('span', { class: 'w-4 shrink-0' })

      const icon = hasChildren
        ? h(isExpanded ? FO : FL, { class: 'size-4 shrink-0 text-amber-500' })
        : h(FT, { class: 'size-4 shrink-0 text-muted-foreground/60' })

      const descendants = props.countDescendants(node)

      const row = h('div', {
        class: 'flex items-center gap-2 px-3 py-2 border-b border-border last:border-0 hover:bg-muted/40 cursor-pointer transition-colors group',
        style: { paddingLeft: `${12 + indent}px` },
        onClick: () => hasChildren ? emit('toggle', node) : emit('navigate', node),
      }, [
        chevron,
        icon,
        h('span', {
          class: 'text-sm text-foreground flex-1 truncate hover:text-primary hover:underline underline-offset-2 transition-colors',
          onClick: (e: Event) => { e.stopPropagation(); emit('navigate', node) },
        }, props.getTitle(node.data)),
        descendants > 0 && h('span', {
          class: 'text-[11px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-medium shrink-0',
        }, String(descendants)),
        h('button', {
          class: 'opacity-0 group-hover:opacity-100 transition-opacity shrink-0 p-1 rounded hover:bg-primary/10 hover:text-primary text-muted-foreground',
          title: 'Add child',
          onClick: (e: Event) => { e.stopPropagation(); emit('create-child', node) },
        }, h(PL, { class: 'size-3.5' })),
      ])

      const children = isExpanded && hasChildren
        ? node.children.map((child: TreeNode) =>
            h(TreeNodeRow, {
              key: child.id,
              node: child,
              depth: depth + 1,
              expandedIds,
              getTitle: props.getTitle,
              countDescendants: props.countDescendants,
              onToggle: (n: any) => emit('toggle', n),
              onNavigate: (n: any) => emit('navigate', n),
              onCreateChild: (n: any) => emit('create-child', n),
            })
          )
        : []

      return [row, ...children]
    }
  },
})

export { TreeNodeRow }
</script>
