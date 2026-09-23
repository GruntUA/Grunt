import { ref, computed, watch, inject, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { DocField } from '@/types'
import { docsApi, metaApi } from '@/core/api'
import type { LinkSearchItem } from '@/core/api/docs'
import type { TreeNode } from '@/components/ui/tree-select'
import { escapeHtml } from '@/lib/utils'
import { useAnchoredDropdown } from '@/core/composables/useAnchoredDropdown'
import { docUrl } from '@/core/workspaceUrl'

export type LinkFiltersFn = (fieldname: string, doc: Record<string, unknown>) => Record<string, string | string[]>

export function useLinkField(props: {
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}, emit: {
  (e: 'update:modelValue', value: unknown): void
  (e: 'create-new', doctype: string, preset: string): void
}) {
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

  // Cache: name → display label
  const displayCache = new Map<string, string>()

  let debounceTimer: ReturnType<typeof setTimeout>
  let blurTimer: ReturnType<typeof setTimeout>

  // Monotonic tokens so a slow response can't overwrite a newer one.
  let searchSeq = 0
  let syncSeq = 0

  const getScriptFilters = inject<LinkFiltersFn>('getLinkFilters', () => ({}))

  // Teleported dropdown, kept anchored to the input on scroll / resize.
  const containerRef = ref<HTMLElement | null>(null)
  const { dropdownStyle, reposition: computeDropdownStyle } = useAnchoredDropdown(isOpen, containerRef)

  onUnmounted(() => {
    clearTimeout(debounceTimer)
    clearTimeout(blurTimer)
  })

  // `link_filters` rarely changes, but resolveFilters() is called on every
  // search, on every activeFilterChips recompute and inside a JSON.stringify
  // watcher — so compile the `eval:` expression / parse the JSON once per
  // distinct raw string instead of rebuilding it each call.
  let compiledRaw: string | undefined
  let compiledEval: ((doc: Record<string, unknown>) => unknown) | null = null
  let compiledJson: Record<string, string> | null = null

  function metaFilters(raw: string, doc: Record<string, unknown>): Record<string, string> {
    if (raw !== compiledRaw) {
      compiledRaw = raw
      compiledEval = null
      compiledJson = null
      const trimmed = raw.trim()
      if (trimmed.startsWith('eval:')) {
        try {
          // eslint-disable-next-line no-new-func
          compiledEval = new Function('doc', `return (${trimmed.slice(5).trim()})`) as (d: Record<string, unknown>) => unknown
        } catch { /* bad expression in metadata */ }
      } else {
        try { compiledJson = JSON.parse(raw) } catch { /* bad JSON in metadata */ }
      }
    }
    if (compiledEval) {
      try {
        const r = compiledEval(doc)
        return typeof r === 'object' && r ? (r as Record<string, string>) : {}
      } catch { return {} }
    }
    return compiledJson ?? {}
  }

  function resolveFilters(): Record<string, string | string[]> {
    const doc = props.doc ?? {}
    const scriptFilters = getScriptFilters(props.field.fieldname, doc)
    const raw = props.field.link_filters
    return { ...(raw ? metaFilters(raw, doc) : {}), ...scriptFilters }
  }

  interface RawTreeNode {
    id: string
    name?: string
    display_title?: string
    children?: RawTreeNode[]
    [key: string]: unknown
  }

  function transformNodes(nodes: RawTreeNode[]): TreeNode[] {
    return nodes.map((node) => ({
      key: node.id,
      label:
        node.display_title ||
        (node[titleField.value] as string | undefined) ||
        node.name ||
        node.id,
      children: node.children?.length ? transformNodes(node.children) : undefined,
    }))
  }

  async function loadTree() {
    if (!props.field.options) return
    treeLoading.value = true
    try {
      let asOf: string | undefined
      if (props.field.options === 'Department') {
        const rawDate = props.doc?.order_date ?? props.doc?.effective_date
        const normalized = String(rawDate ?? '').slice(0, 10)
        if (normalized) asOf = normalized
      }

      const raw = await docsApi.getTree(props.field.options, asOf ? { as_of: asOf } : undefined)
      treeNodes.value = transformNodes(raw)
    } catch {
      treeNodes.value = []
    } finally {
      treeLoading.value = false
    }
  }

  function onTreeSelect(key: string | null) {
    emit('update:modelValue', key)
  }

  async function resolveDisplay(value: string): Promise<string> {
    if (!value || !props.field.options) return value
    if (displayCache.has(value)) return displayCache.get(value)!

    if (titleField.value === 'name') {
      displayCache.set(value, value)
      return value
    }

    try {
      const hits = await docsApi.linkSearch(props.field.options, value, {}, 5)
      const match = hits.find(r => r.name === value || r.id === value)
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
    const seq = ++syncSeq
    if (!raw) { query.value = ''; return }

    if (displayCache.has(raw)) { query.value = displayCache.get(raw)!; return }

    // The parent (form / child-table row) usually already carries the resolved
    // label as `<fieldname>__label` — use it instead of a network round-trip,
    // but only while it still matches the field's current value.
    const docLabel = props.doc?.[`${props.field.fieldname}__label`]
    if (
      typeof docLabel === 'string' && docLabel &&
      String(props.doc?.[props.field.fieldname] ?? '') === raw
    ) {
      displayCache.set(raw, docLabel)
      query.value = docLabel
      return
    }

    query.value = raw
    const display = await resolveDisplay(raw)
    if (seq === syncSeq) query.value = display
  }

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

  watch(
    () => [props.doc?.order_date, props.doc?.effective_date],
    () => {
      if (isTree.value && props.field.options === 'Department') {
        loadTree()
      }
    },
  )

  async function search(val: string) {
    if (!props.field.options) return
    const seq = ++searchSeq
    isLoading.value = true
    try {
      const hits = await docsApi.linkSearch(props.field.options, val, resolveFilters())
      if (seq !== searchSeq) return // a newer search already superseded this one
      results.value = hits
      activeIdx.value = -1
      isOpen.value = true
    } catch {
      if (seq === searchSeq) results.value = []
    } finally {
      if (seq === searchSeq) isLoading.value = false
    }
  }

  function onInput(val: string) {
    query.value = val
    clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => search(val), val ? 300 : 0)
  }

  function onFocus() {
    clearTimeout(blurTimer)
    computeDropdownStyle()
    // When a value is already picked, `query` holds its label — searching for
    // that exact string just echoes the one row back. Open the default list
    // instead so the user can switch to another record.
    if (!isOpen.value) search(isSelected.value ? '' : query.value)
  }

  function onBlur() {
    blurTimer = setTimeout(() => {
      isOpen.value = false
      syncQueryFromValue(props.modelValue)
    }, 200)
  }

  // When the typed text already names an existing record (by label or id),
  // creating "the same thing" again is meaningless — hide the create row.
  const hasExactMatch = computed(() => {
    const q = query.value.trim().toLowerCase()
    if (!q) return false
    return results.value.some(
      (r) => r.title.trim().toLowerCase() === q || r.name.toLowerCase() === q,
    )
  })

  const canCreate = computed(() =>
    !!(props.field.options && !props.disabled && !props.field.read_only) &&
    !hasExactMatch.value
  )

  const totalItems = computed(() => results.value.length + (canCreate.value ? 1 : 0))

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

  function createNew() {
    if (!props.field.options) return
    isOpen.value = false
    emit('create-new', props.field.options, query.value)
  }

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

  // Returns an HTML string for v-html: the source text is always HTML-escaped
  // first (record titles are user data), then the query match is wrapped.
  function highlight(text: string): string {
    const safe = escapeHtml(text ?? '')
    if (!query.value.trim()) return safe
    const escaped = query.value.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    return safe.replace(
      new RegExp(`(${escaped})`, 'gi'),
      '<mark class="bg-primary/20 text-foreground rounded-sm">$1</mark>',
    )
  }

  const isSelected = computed(
    () => props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== '',
  )

  const filterChipLabels = ref<Map<string, string>>(new Map())

  async function resolveFilterChipLabels() {
    const filters = resolveFilters()
    if (!props.field.options || !Object.keys(filters).length) return

    for (const [key, value] of Object.entries(filters)) {
      if (key.endsWith('__in')) continue

      const cacheKey = `${key}:${String(value)}`
      if (filterChipLabels.value.has(cacheKey)) continue

      const docLabel = props.doc?.[`${key}__label`] as string | undefined
      if (docLabel) {
        filterChipLabels.value.set(cacheKey, docLabel)
        continue
      }

      try {
        const meta = await metaApi.get(props.field.options)
        const filterField = meta.fields.find((f) => f.fieldname === key)
        if (filterField?.fieldtype === 'Link' && filterField.options) {
          const hits = await docsApi.linkSearch(filterField.options, String(value), {}, 5)
          const match = hits.find(r => r.name === String(value) || r.id === String(value))
          if (match) {
            filterChipLabels.value.set(cacheKey, match.title)
            continue
          }
        }
      } catch { /* ignore */ }

      filterChipLabels.value.set(cacheKey, String(value))
    }
  }

  watch(
    () => JSON.stringify(resolveFilters()),
    () => { void resolveFilterChipLabels() },
    { immediate: true },
  )

  const activeFilterChips = computed(() =>
    Object.entries(resolveFilters()).map(([key, value]) => {
      if (key.endsWith('__in') && Array.isArray(value)) {
        return { key, display: t('{n} available', { n: value.length }) }
      }
      const cacheKey = `${key}:${String(value)}`
      return { key, display: filterChipLabels.value.get(cacheKey) ?? String(value) }
    })
  )

  const linkedDocUrl = computed(() => {
    if (!isSelected.value || !props.field.options || !props.modelValue) return null
    const workspace = route.params.workspaceName as string | undefined
    if (workspace) return docUrl(props.field.options, props.modelValue, workspace)
    return null
  })

  function openLinkedDoc() {
    if (linkedDocUrl.value) router.push(linkedDocUrl.value)
  }

  return {
    t,
    query,
    results,
    isOpen,
    isLoading,
    activeIdx,
    containerRef,
    dropdownStyle,
    isTree,
    treeNodes,
    treeLoading,
    canCreate,
    isSelected,
    activeFilterChips,
    linkedDocUrl,
    onTreeSelect,
    onInput,
    onFocus,
    onBlur,
    onKeydown,
    select,
    clear,
    createNew,
    highlight,
    openLinkedDoc,
  }
}
