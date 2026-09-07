<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { docsApi } from '@/core/api/docs'
import { ChevronRight, ChevronDown, Plus, FolderOpen, AlertCircle } from '@lucide/vue'
import type { DocType, QuickFilter, ActiveFilter } from '@/types'
import QuickEntryDialog from '@/components/views/QuickEntryDialog.vue'
import { useQuickFilters } from '@/core/composables/useQuickFilters'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'

const props = defineProps<{
  doctype: DocType
  parentField: string
  workspace?: string
  quickFilterDefs?: QuickFilter[]
  quickFilterValues?: Record<string, string>
  activeFilters?: ActiveFilter[]
  refreshKey?: number
}>()

const emit = defineEmits<{
  (e: 'update:quickFilterValues', val: Record<string, string>): void
  (e: 'update:activeFilters', val: ActiveFilter[]): void
}>()

const { t } = useI18n()
const router = useRouter()

// ── Quick filter state ────────────────────────────────────────────────────────
const _ffValues = ref<Record<string, string>>(props.quickFilterValues ?? {})

watch(() => props.quickFilterValues, (v) => {
  if (v !== undefined) _ffValues.value = v
}, { deep: true, immediate: true })

watch(_ffValues, (v) => {
  emit('update:quickFilterValues', v)
}, { deep: true })

const ffDefs = computed<QuickFilter[]>(() => props.quickFilterDefs ?? [])

const { rawQuickFilters } = useQuickFilters(ffDefs, 'tree', _ffValues)

// ── As-of date (from tree_as_of_date_field) ──────────────────────────────────
const asOfField = computed(() => props.doctype.tree_as_of_date_field ?? null)
const asOf = computed(() => _ffValues.value.as_of_date ?? '')

// ── Sorting (metadata defaults + runtime override) ───────────────────────────
const defaultSortBy = computed(() =>
  props.doctype.tree_sort_by
  ?? props.doctype.tree_title_field
  ?? props.doctype.title_field
  ?? 'name'
)

const defaultSortOrder = computed<'asc' | 'desc'>(() =>
  props.doctype.tree_sort_order === 'desc' ? 'desc' : 'asc'
)

const sortBy = ref(defaultSortBy.value)
const sortOrder = ref<'asc' | 'desc'>(defaultSortOrder.value)

watch(() => props.doctype.name, () => {
  sortBy.value = defaultSortBy.value
  sortOrder.value = defaultSortOrder.value
})

const sortFieldOptions = computed(() => {
  const base = [
    'name',
    props.doctype.tree_title_field,
    props.doctype.title_field,
    props.doctype.tree_sort_by,
  ].filter((v): v is string => Boolean(v && v.trim()))

  const metadata = props.doctype.fields
    .filter((f) => !['Section', 'Column', 'Tab', 'Table'].includes(f.fieldtype))
    .map((f) => f.fieldname)

  return Array.from(new Set([...base, ...metadata]))
})

const sortFieldLabel = computed<Record<string, string>>(() => {
  const labels: Record<string, string> = {}
  for (const f of props.doctype.fields) labels[f.fieldname] = f.label || f.fieldname
  labels.name = labels.name || 'name'
  return labels
})

// ── Tree state ───────────────────────────────────────────────────────────────
const treeNodes = ref<any[]>([])
const loading = ref(false)
const error = ref('')

// ── Expanded IDs persistence ─────────────────────────────────────────────────
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

// ── Active filters (FilterBar) ───────────────────────────────────────────────
const _activeFilters = ref<ActiveFilter[]>(props.activeFilters ?? [])

watch(() => props.activeFilters, (v) => {
  if (v !== undefined) _activeFilters.value = v
}, { deep: true, immediate: true })

watch(_activeFilters, (v) => {
  emit('update:activeFilters', v)
}, { deep: true })

// ── Data fetching ────────────────────────────────────────────────────────────
async function loadTree() {
  loading.value = true
  error.value = ''
  try {
    const ffRaw = Object.keys(rawQuickFilters.value).length ? rawQuickFilters.value : undefined
    // Merge as_of date as a raw filter on the designated field (tree_as_of_date_field)
    const dateFilter: Record<string, string> | undefined =
      asOf.value && asOfField.value
        ? { [`${asOfField.value}__lte`]: asOf.value }
        : undefined
    const mergedQuickFilters = (ffRaw || dateFilter)
      ? { ...(ffRaw ?? {}), ...(dateFilter ?? {}) }
      : undefined

    treeNodes.value = await docsApi.getTree(props.doctype.name, {
      quickFilters: mergedQuickFilters,
      as_of: asOf.value || undefined,
      filters: _activeFilters.value.length ? _activeFilters.value : undefined,
      sort_by: sortBy.value || undefined,
      sort_order: sortOrder.value,
    })
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : t('Load error')
  } finally {
    loading.value = false
  }
}

watch(rawQuickFilters, () => loadTree(), { deep: true })
watch(_activeFilters, () => loadTree(), { deep: true })
watch(sortBy, () => loadTree())
watch(sortOrder, () => loadTree())
// Bumped by the shared header's Refresh button (tree data isn't on the shared query cache).
watch(() => props.refreshKey, (_v, old) => { if (old !== undefined) loadTree() })
onMounted(loadTree)

// ── Helpers ──────────────────────────────────────────────────────────────────
const titleField = computed(() =>
  props.doctype.tree_title_field
  ?? props.doctype.title_field
  ?? props.doctype.fields.find(f => f.fieldtype === 'Text' && f.in_list_view)?.fieldname
  ?? 'name'
)

function getTitle(node: any): string {
  if (node.display_title) return String(node.display_title)
  const v = node[titleField.value]
  if (v !== null && v !== undefined) return String(v)
  return node.name ?? String(node.id)
}

function countDescendants(node: any): number {
  const children: any[] = node.children ?? []
  let count = children.length
  for (const child of children) count += countDescendants(child)
  return count
}

// ── Interactions ─────────────────────────────────────────────────────────────
function toggle(node: any) {
  const id = String(node.id)
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
  expandedIds.value = new Set(expandedIds.value)
  saveExpandedIds(expandedIds.value)
}

function expandAll(nodes: any[] = treeNodes.value) {
  for (const n of nodes) {
    const children: any[] = n.children ?? []
    if (children.length) {
      expandedIds.value.add(String(n.id))
      expandAll(children)
    }
  }
  expandedIds.value = new Set(expandedIds.value)
  saveExpandedIds(expandedIds.value)
}

function collapseAll() {
  expandedIds.value = new Set()
  saveExpandedIds(expandedIds.value)
}

function toggleSortOrder() {
  sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
}

function navigateTo(node: any) {
  if (props.workspace) {
    router.push(`/${props.workspace}/${props.doctype.name}/${node.id}`)
  } else {
    router.push(`/${props.doctype.name}/${node.id}`)
  }
}

// ── Quick entry ───────────────────────────────────────────────────────────────
const quickEntryPreset = ref<Record<string, unknown> | null>(null)

function createChild(parentNode: any) {
  quickEntryPreset.value = { [props.parentField]: parentNode.id }
}

function onQuickEntrySaved() {
  quickEntryPreset.value = null
  loadTree()
}

function createRoot() {
  if (props.workspace) {
    router.push(`/${props.workspace}/${props.doctype.name}/new`)
  } else {
    router.push(`/${props.doctype.name}/new`)
  }
}

const totalCount = computed(() => {
  let n = 0
  const countAll = (nodes: any[]) => { for (const node of nodes) { n++; countAll(node.children ?? []) } }
  countAll(treeNodes.value)
  return n
})
</script>

<template>
  <div>
    <!-- Tree controls -->
    <div class="flex items-center gap-2 mb-4 flex-wrap">
      <Button variant="ghost" size="sm" @click="expandAll()">
        <ChevronDown class="size-3.5 mr-1" />
        Розгорнути все
      </Button>
      <Button variant="ghost" size="sm" @click="collapseAll">
        <ChevronRight class="size-3.5 mr-1" />
        Згорнути все
      </Button>
      <select
        v-model="sortBy"
        class="h-8 rounded-md border border-border bg-background px-2 text-foreground"
        :title="t('Sort by')"
      >
        <option v-for="field in sortFieldOptions" :key="field" :value="field">
          {{ sortFieldLabel[field] ?? field }}
        </option>
      </select>
      <Button variant="ghost" size="sm" @click="toggleSortOrder" :title="t('Sort order')">
        {{ sortOrder === 'asc' ? 'A-Z' : 'Z-A' }}
      </Button>
    </div>

    <!-- Loading -->
    <div v-if="loading && !treeNodes.length" class="flex justify-center py-16">
      <Spinner class="size-10!" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex items-center gap-3 p-4 rounded-lg bg-destructive/10 text-destructive">
      <AlertCircle class="size-4 shrink-0" />
      {{ error }}
      <Button variant="ghost" size="sm" class="ml-auto" @click="loadTree">{{ t('Retry') }}</Button>
    </div>

    <!-- Empty -->
    <div v-else-if="!loading && !treeNodes.length"
      class="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
      <FolderOpen class="size-12 opacity-30" />
      <p>Записів поки немає</p>
      <Button size="sm" @click="createRoot">
        <Plus class="size-4 mr-1.5" />
        Створити перший
      </Button>
    </div>

    <!-- Tree -->
    <div v-else class="border border-border rounded-lg overflow-hidden bg-card shadow-sm">
      <TreeNodeRow v-for="node in treeNodes" :key="node.id" :node="node" :depth="0" :expanded-ids="expandedIds"
        :get-title="getTitle" :count-descendants="countDescendants" @toggle="toggle" @navigate="navigateTo"
        @create-child="createChild" />
    </div>

    <!-- Counter -->
    <p v-if="totalCount" class="mt-3 text-muted-foreground text-right">
      Всього: {{ totalCount }} записів
    </p>

    <!-- Quick entry dialog -->
    <QuickEntryDialog v-if="quickEntryPreset !== null" :dt="doctype" :preset="quickEntryPreset" :workspace="workspace"
      mode="list" @close="quickEntryPreset = null" @saved="onQuickEntrySaved" />
  </div>
</template>

<!-- ── Recursive tree node component ─────────────────────────────────────── -->
<script lang="ts">
import { defineComponent, h, type PropType } from 'vue'
import { ChevronRight as CR, ChevronDown as CD, Plus as PL, Folder as FL, FolderOpen as FO, FileText as FT } from '@lucide/vue'

interface TreeNode {
  id: string
  children: TreeNode[]
  [key: string]: unknown
}

const TreeNodeRow: any = defineComponent({
  name: 'TreeNodeRow',
  props: {
    node: { type: Object as PropType<TreeNode>, required: true },
    depth: { type: Number, required: true },
    expandedIds: { type: Object as PropType<Set<string>>, required: true },
    getTitle: { type: Function as PropType<(node: any) => string>, required: true },
    countDescendants: { type: Function as PropType<(node: any) => number>, required: true },
  },
  emits: ['toggle', 'navigate', 'create-child'],
  setup(props, { emit }) {
    return () => {
      const { node, depth, expandedIds } = props
      const isExpanded = expandedIds.has(String(node.id))
      const children: TreeNode[] = (node.children ?? []) as TreeNode[]
      const hasChildren = children.length > 0
      const indent = depth * 20

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
        }, props.getTitle(node)),
        descendants > 0 && h('span', {
          class: 'px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-medium shrink-0',
        }, String(descendants)),
        h('button', {
          class: 'opacity-0 group-hover:opacity-100 transition-opacity shrink-0 p-1 rounded hover:bg-primary/10 hover:text-primary text-muted-foreground',
          title: 'Add child',
          onClick: (e: Event) => { e.stopPropagation(); emit('create-child', node) },
        }, h(PL, { class: 'size-3.5' })),
      ])

      const childRows = isExpanded && hasChildren
        ? children.map((child: TreeNode) =>
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

      return [row, ...childRows]
    }
  },
})

export { TreeNodeRow }
</script>
