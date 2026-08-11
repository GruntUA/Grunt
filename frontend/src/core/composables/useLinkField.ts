import { ref, computed, watch, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { DocField } from '@/types'
import { docsApi, metaApi } from '@/core/api'
import type { LinkSearchItem } from '@/core/api/docs'
import type { TreeNode } from '@/components/ui/tree-select'

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

  const containerRef = ref<HTMLElement | null>(null)
  const dropdownStyle = ref<Record<string, string>>({})

  // Tree mode
  const isTree = ref(false)
  const treeNodes = ref<TreeNode[]>([])
  const treeLoading = ref(false)

  // Cache: name → display label
  const displayCache = new Map<string, string>()

  let debounceTimer: ReturnType<typeof setTimeout>
  let blurTimer: ReturnType<typeof setTimeout>

  const getScriptFilters = inject<LinkFiltersFn>('getLinkFilters', () => ({}))

  function computeDropdownStyle() {
    if (!containerRef.value) return
    const rect = containerRef.value.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom - 4
    const openUp = spaceBelow < 120 && rect.top > spaceBelow
    dropdownStyle.value = {
      position: 'fixed',
      left: `${rect.left}px`,
      width: `${rect.width}px`,
      zIndex: '9999',
      ...(openUp
        ? { bottom: `${window.innerHeight - rect.top + 4}px` }
        : { top: `${rect.bottom + 4}px` }),
    }
  }

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

  function transformNodes(nodes: any[]): TreeNode[] {
    return nodes.map(node => ({
      key: node.id,
      label: node.display_title || node[titleField.value] || node.name || node.id,
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
    if (!raw) { query.value = ''; return }
    query.value = raw
    query.value = await resolveDisplay(raw)
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
    computeDropdownStyle()
    if (!isOpen.value) search(query.value)
  }

  function onBlur() {
    blurTimer = setTimeout(() => {
      isOpen.value = false
      syncQueryFromValue(props.modelValue)
    }, 200)
  }

  const canCreate = computed(() =>
    !!(props.field.options && !props.disabled && !props.field.read_only)
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
