<script setup lang="ts">
import { ref, watch, computed, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { DocField } from '@/types'
import { docsApi, metaApi } from '@/core/api'
import type { LinkSearchItem } from '@/core/api/docs'
import { Search, X, Loader2, Plus, ArrowUpRight } from '@lucide/vue'
import TreeSelect from 'primevue/treeselect'
import type { TreeNode } from 'primevue/treenode'

const props = defineProps<{
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  /** Current document values — used to evaluate link_filters with "eval:" prefix. */
  doc?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  'create-new': [doctype: string, preset: string]
}>()

// ── State ─────────────────────────────────────────────────────────────────────

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const query = ref('')
const results = ref<LinkSearchItem[]>([])
const isOpen = ref(false)
const isLoading = ref(false)
const activeIdx = ref(-1)
const titleField = ref<string>('name')

// Tree mode
const isTree = ref(false)
const treeNodes = ref<TreeNode[]>([])
const treeLoading = ref(false)
const expandedKeys = ref<Record<string, boolean>>({})

// Cache: name → display label
const displayCache = new Map<string, string>()

let debounceTimer: ReturnType<typeof setTimeout>
let blurTimer: ReturnType<typeof setTimeout>

// ── Script-registered filters (from frm.set_query) ───────────────────────────

type LinkFiltersFn = (fieldname: string, doc: Record<string, unknown>) => Record<string, string | string[]>
const getScriptFilters = inject<LinkFiltersFn>('getLinkFilters', () => ({}))

// ── Resolve link_filters ──────────────────────────────────────────────────────

function resolveFilters(): Record<string, string | string[]> {
  const doc = props.doc ?? {}
  const scriptFilters = getScriptFilters(props.field.fieldname, doc)
  let metaFilters: Record<string, string> = {}
  const raw = props.field.link_filters
  if (raw) {
    try {
      if (raw.trim().startsWith('eval:')) {
        const expr = raw.trim().slice(5).trim()
        // eslint-disable-next-line no-new-func
        const result = new Function('doc', `return (${expr})`)(doc)
        metaFilters = typeof result === 'object' && result ? result : {}
      } else {
        metaFilters = JSON.parse(raw)
      }
    } catch { /* ignore */ }
  }
  return { ...metaFilters, ...scriptFilters }
}

// ── Tree helpers ──────────────────────────────────────────────────────────────

function transformNodes(nodes: any[]): TreeNode[] {
  return nodes.map(node => ({
    key: node.id,
    label: node[titleField.value] || node.name || node.id,
    data: node,
    children: node.children?.length ? transformNodes(node.children) : undefined,
    leaf: !node.children?.length,
  }))
}

/** Recursively find and expand the path to a node with the given key. */
function expandToSelection(key: string, nodes: TreeNode[]): boolean {
  for (const node of nodes) {
    if (node.key === key) return true
    if (node.children?.length) {
      if (expandToSelection(key, node.children)) {
        expandedKeys.value[String(node.key)] = true
        return true
      }
    }
  }
  return false
}

async function loadTree() {
  if (!props.field.options) return
  treeLoading.value = true
  try {
    const raw = await docsApi.getTree(props.field.options)
    treeNodes.value = transformNodes(raw)
    
    // Auto-expand to current selection
    if (props.modelValue) {
      expandToSelection(String(props.modelValue), treeNodes.value)
    }
  } catch {
    treeNodes.value = []
  } finally {
    treeLoading.value = false
  }
}

// TreeSelect v-model is { [key]: true } for single selection mode
const treeSelection = computed<Record<string, boolean> | null>({
  get() {
    const v = props.modelValue
    if (!v || v === '') return null
    return { [String(v)]: true }
  },
  set(val) {
    if (!val || Object.keys(val).length === 0) {
      emit('update:modelValue', null)
    } else {
      const selectedKey = Object.keys(val)[0]
      emit('update:modelValue', selectedKey)
      // On selection, also expand the node's lineage (in case filter was used)
      expandToSelection(selectedKey, treeNodes.value)
    }
  },
})

// ── Resolve display label for a stored value ─────────────────────────────────

async function resolveDisplay(value: string): Promise<string> {
  if (!value || !props.field.options) return value
  if (displayCache.has(value)) return displayCache.get(value)!

  if (titleField.value === 'name') {
    displayCache.set(value, value)
    return value
  }

  // Use link_search to resolve display — avoids 404s for missing records
  try {
    const results = await docsApi.linkSearch(props.field.options, value, {}, 5)
    const match = results.find(r => r.name === value || r.id === value)
    const display = match?.title ?? value
    displayCache.set(value, display)
    return display
  } catch {
    displayCache.set(value, value)
    return value
  }
}

async function syncQueryFromValue(v: unknown) {
  const raw = String(v ?? '')
  if (!raw) { query.value = ''; return }
  query.value = raw
  query.value = await resolveDisplay(raw)
}

// ── Sync value → display ──────────────────────────────────────────────────────

watch(() => props.modelValue, (v) => {
  if (!isTree.value) syncQueryFromValue(v)
})

watch(() => props.field.options, async (doctype) => {
  if (!doctype) return
  try {
    const meta = await metaApi.get(doctype)
    titleField.value = meta.title_field || 'name'
    isTree.value = !!meta.is_tree
    if (isTree.value) {
      await loadTree()
    }
  } catch {
    titleField.value = 'name'
    isTree.value = false
  }
  if (!isTree.value && props.modelValue) syncQueryFromValue(props.modelValue)
}, { immediate: true })

// ── Search via dedicated link_search endpoint ─────────────────────────────────

async function search(val: string) {
  if (!props.field.options) return
  isLoading.value = true
  try {
    results.value = await docsApi.linkSearch(
      props.field.options,
      val,
      resolveFilters(),
    )
    activeIdx.value = -1
    isOpen.value = true
  } catch {
    results.value = []
  } finally {
    isLoading.value = false
  }
}

function onInput(val: string) {
  query.value = val
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => search(val), val ? 300 : 0)
}

function onFocus() {
  clearTimeout(blurTimer)
  if (!isOpen.value) search(query.value)
}

function onBlur() {
  blurTimer = setTimeout(() => {
    isOpen.value = false
    syncQueryFromValue(props.modelValue)
  }, 200)
}

// ── Keyboard navigation ───────────────────────────────────────────────────────

const totalItems = computed(() => results.value.length + (canCreate.value ? 1 : 0))

function onKeydown(e: KeyboardEvent) {
  if (!isOpen.value) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIdx.value = Math.min(activeIdx.value + 1, totalItems.value - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIdx.value = Math.max(activeIdx.value - 1, -1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (activeIdx.value === results.value.length && canCreate.value) {
      createNew()
    } else if (activeIdx.value >= 0 && results.value[activeIdx.value]) {
      select(results.value[activeIdx.value])
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    isOpen.value = false
    syncQueryFromValue(props.modelValue)
  }
}

// ── Selection ─────────────────────────────────────────────────────────────────

function select(item: LinkSearchItem) {
  displayCache.set(item.name, item.title)
  query.value = item.title
  emit('update:modelValue', item.name)
  isOpen.value = false
}

function clear() {
  query.value = ''
  emit('update:modelValue', null)
  isOpen.value = false
}

// ── Create new ────────────────────────────────────────────────────────────────

const canCreate = computed(() =>
  !!(props.field.options && !props.disabled && !props.field.read_only)
)

function createNew() {
  if (!props.field.options) return
  isOpen.value = false
  emit('create-new', props.field.options, query.value)
}

// ── Highlight ─────────────────────────────────────────────────────────────────

function highlight(text: string): string {
  if (!query.value.trim()) return text
  const escaped = query.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(
    new RegExp(`(${escaped})`, 'gi'),
    '<mark class="bg-primary/20 text-foreground rounded-sm">$1</mark>',
  )
}

const isSelected = computed(
  () => props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== '',
)

// ── Active filter chips ───────────────────────────────────────────────────────

const filterChipLabels = ref<Map<string, string>>(new Map())

async function resolveFilterChipLabels() {
  const filters = resolveFilters()
  if (!props.field.options || !Object.keys(filters).length) return

  for (const [key, value] of Object.entries(filters)) {
    // Skip __in filters — show count summary chip, no need to resolve
    if (key.endsWith('__in')) continue

    const cacheKey = `${key}:${String(value)}`
    if (filterChipLabels.value.has(cacheKey)) continue

    // 1. Try label already in doc (e.g. loaded from server with __label suffix)
    const docLabel = props.doc?.[`${key}__label`] as string | undefined
    if (docLabel) {
      filterChipLabels.value.set(cacheKey, docLabel)
      continue
    }

    // 2. Look up via linked doctype’s field metadata to find the target doctype,
    //    then resolve via link_search
    try {
      const meta = await metaApi.get(props.field.options)
      const filterField = meta.fields.find((f: any) => f.fieldname === key)
      if (filterField?.fieldtype === 'Link' && filterField.options) {
        const hits = await docsApi.linkSearch(filterField.options, String(value), {}, 5)
        const match = hits.find(r => r.name === String(value) || r.id === String(value))
        if (match) {
          filterChipLabels.value.set(cacheKey, match.title)
          continue
        }
      }
    } catch { /* ignore */ }

    // 3. Fallback to raw value
    filterChipLabels.value.set(cacheKey, String(value))
  }
}

// Re-resolve when filters change (e.g. user picks a different department)
watch(
  () => JSON.stringify(resolveFilters()),
  () => { void resolveFilterChipLabels() },
  { immediate: true },
)

const activeFilterChips = computed(() =>
  Object.entries(resolveFilters()).map(([key, value]) => {
    if (key.endsWith('__in') && Array.isArray(value)) {
      return { key, display: `${value.length} доступних` }
    }
    const cacheKey = `${key}:${String(value)}`
    return { key, display: filterChipLabels.value.get(cacheKey) ?? String(value) }
  })
)

const linkedDocUrl = computed(() => {
  if (!isSelected.value || !props.field.options || !props.modelValue) return null
  const workspace = route.params.workspaceName as string | undefined
  if (workspace) return `/${workspace}/${props.field.options}/${props.modelValue}`
  return null
})

function openLinkedDoc() {
  if (linkedDocUrl.value) router.push(linkedDocUrl.value)
}
</script>

<template>
  <!-- Tree mode: use PrimeVue TreeSelect -->
  <div v-if="isTree" class="relative flex items-center gap-1">
    <TreeSelect
      v-model="treeSelection"
      v-model:expanded-keys="expandedKeys"
      :options="treeNodes"
      :loading="treeLoading"
      :disabled="disabled || field.read_only"
      selection-mode="single"
      filter
      show-clear
      :placeholder="field.placeholder ?? `Оберіть ${field.options ?? ''}...`"
      :class="[
        'w-full',
        error ? 'p-invalid' : '',
      ]"
      @clear="emit('update:modelValue', null)"
    />
    <button
      v-if="isSelected && linkedDocUrl"
      type="button"
      class="shrink-0 text-muted-foreground hover:text-primary transition-colors"
      :title="t('Open {doctype}', { doctype: field.options ?? '' })"
      @click="openLinkedDoc"
    >
      <ArrowUpRight class="size-4" />
    </button>
  </div>

  <!-- Regular mode: custom input + dropdown -->
  <div v-else class="relative">
    <div class="relative">
      <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />

      <input
        :value="query"
        :placeholder="field.placeholder ?? `Пошук ${field.options ?? ''}...`"
        :disabled="disabled || field.read_only"
        :class="[
          'w-full rounded-md border border-input bg-transparent pl-8 py-2 text-sm text-foreground ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-ring disabled:bg-muted disabled:cursor-not-allowed transition-colors',
          isSelected && linkedDocUrl ? 'pr-16' : 'pr-8',
          error ? 'border-destructive focus-visible:ring-destructive' : '',
        ]"
        autocomplete="off"
        @input="onInput(($event.target as HTMLInputElement).value)"
        @focus="onFocus"
        @blur="onBlur"
        @keydown="onKeydown"
      />

      <div class="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center gap-1">
        <Loader2 v-if="isLoading" class="size-4 text-muted-foreground animate-spin" />
        <template v-else-if="isSelected">
          <button
            v-if="linkedDocUrl"
            type="button"
            class="text-muted-foreground hover:text-primary transition-colors"
            :title="t('Open {doctype}', { doctype: field.options ?? '' })"
            @mousedown.prevent="openLinkedDoc"
          >
            <ArrowUpRight class="size-4" />
          </button>
          <button
            v-if="!disabled && !field.read_only"
            type="button"
            class="text-muted-foreground hover:text-foreground transition-colors"
            @mousedown.prevent="clear"
          >
            <X class="size-4" />
          </button>
        </template>
      </div>
    </div>

    <div
      v-if="isOpen"
      class="absolute top-full mt-1 left-0 right-0 bg-popover border border-border rounded-lg shadow-lg z-50 overflow-hidden"
    >
      <div v-if="results.length" class="max-h-52 overflow-y-auto py-1">
        <button
          v-for="(item, i) in results"
          :key="item.id"
          type="button"
          :class="[
            'w-full text-left px-3 py-2 text-sm transition-colors flex flex-col gap-0.5',
            i === activeIdx ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
          ]"
          @mousedown.prevent="select(item)"
          @mouseover="activeIdx = i"
        >
          <span v-html="highlight(item.title)" />
          <span
            v-if="item.subtitle"
            class="text-xs text-muted-foreground"
            v-html="highlight(item.subtitle)"
          />
        </button>
      </div>

      <div v-else class="px-3 py-3 text-sm text-muted-foreground text-center">
        <span v-if="isLoading">{{ t('Searching...') }}</span>
        <span v-else-if="query">Нічого не знайдено для «{{ query }}»</span>
        <span v-else>{{ t('No records') }}</span>
      </div>

      <template v-if="canCreate">
        <div class="border-t border-border" />
        <button
          type="button"
          :class="[
            'w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors',
            activeIdx === results.length
              ? 'bg-accent text-accent-foreground'
              : 'text-primary hover:bg-accent/50',
          ]"
          @mousedown.prevent="createNew"
          @mouseover="activeIdx = results.length"
        >
          <Plus class="size-3.5 shrink-0" />
          <span v-if="query">
            {{ t('Create') }} <strong>{{ query }}</strong>
            <span class="text-muted-foreground text-xs ml-1">({{ field.options }})</span>
          </span>
          <span v-else class="text-muted-foreground">
            {{ t('Create new') }} {{ field.options }}
          </span>
        </button>
      </template>

      <template v-if="activeFilterChips.length">
        <div class="border-t border-border" />
        <div class="px-3 py-1.5 flex items-center gap-1.5 flex-wrap">
          <span class="text-xs text-muted-foreground">Фільтр:</span>
          <span
            v-for="chip in activeFilterChips"
            :key="chip.key"
            class="inline-flex items-center text-xs bg-primary/10 text-primary rounded px-1.5 py-0.5 font-medium"
          >
            {{ chip.display }}
          </span>
        </div>
      </template>
    </div>
  </div>
</template>
