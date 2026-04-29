import { watch } from 'vue'
import type { Ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import type { DocType } from '@/types'

interface UseListRouteSyncOptions {
  route: RouteLocationNormalizedLoaded
  router: Router
  viewMode: Ref<string>
  groupBy: Ref<string | null>
  sortKey: Ref<string>
  sortOrder: Ref<'asc' | 'desc'>
  activeFilters: Ref<any[]>
  fastFilterValues?: Ref<Record<string, string>>
  validViews: readonly string[]
  getDefaultView: () => string
  dt: Ref<DocType | null>
}

const OP_MAP: Record<string, string> = {
  '=': 'eq', '!=': 'ne', 'like': 'ilike',
  '>': 'gt', '<': 'lt', '>=': 'gte', '<=': 'lte',
}

const REVERSE_OP_MAP: Record<string, string> = Object.fromEntries(
  Object.entries(OP_MAP).map(([display, backend]) => [backend, display])
)

export function useListRouteSync(options: UseListRouteSyncOptions) {
  // Sync state to URL
  watch([options.viewMode, options.activeFilters, options.fastFilterValues], () => {
    const query = { ...options.route.query }

    // View mode
    if (options.viewMode.value === options.getDefaultView()) delete query.view
    else query.view = options.viewMode.value

    // Regular filters
    Object.keys(query).forEach(k => {
      if (k.startsWith('filter[')) delete query[k]
    })
    options.activeFilters.value.forEach(f => {
      const backendOp = OP_MAP[f.op] ?? 'eq'
      query[`filter[${f.fieldname}__${backendOp}]`] = f.value
    })

    // Fast filters
    Object.keys(query).forEach(k => {
      if (k.startsWith('ff[')) delete query[k]
    })
    if (options.fastFilterValues) {
      Object.entries(options.fastFilterValues.value).forEach(([id, val]) => {
        if (val !== '' && val != null) query[`ff[${id}]`] = val
      })
    }

    options.router.replace({ query })
  }, { deep: true })

  function applyRouteState() {
    const urlView = options.route.query.view as string | undefined

    if (urlView && options.validViews.includes(urlView)) {
      options.viewMode.value = urlView as any
    } else if (!options.validViews.includes(options.viewMode.value)) {
      options.viewMode.value = options.getDefaultView() as any
    }

    if (options.route.query.groupBy) options.groupBy.value = options.route.query.groupBy as string
    if (options.route.query.sort) options.sortKey.value = options.route.query.sort as string
    if (['asc', 'desc'].includes(options.route.query.order as string)) {
      options.sortOrder.value = options.route.query.order as 'asc' | 'desc'
    }

    // Parse filters from URL: filter[fieldname__op]=value
    const filters: any[] = []
    Object.entries(options.route.query).forEach(([key, value]) => {
      const match = key.match(/^filter\[(.+)\]$/)
      if (match && value) {
        const fullKey = match[1]
        const parts = fullKey.split('__')
        const fieldname = parts[0]
        const backendOp = parts[1] || 'eq'

        const field = options.dt.value?.fields.find(f => f.fieldname === fieldname)
        const label = field?.label || fieldname
        const fieldtype = field?.fieldtype
        const op = REVERSE_OP_MAP[backendOp] || '='

        filters.push({
          fieldname,
          op,
          value: String(value),
          label,
          fieldtype,
        })
      }
    })

    if (filters.length > 0) {
      options.activeFilters.value = filters
    }

    // Parse fast filter values from URL: ff[id]=value
    const ffValues: Record<string, string> = {}
    Object.entries(options.route.query).forEach(([key, value]) => {
      const match = key.match(/^ff\[(.+)\]$/)
      if (match && value) ffValues[match[1]] = String(value)
    })
    if (Object.keys(ffValues).length > 0 && options.fastFilterValues) {
      options.fastFilterValues.value = { ...options.fastFilterValues.value, ...ffValues }
    }
  }

  function setGroupByInRoute(field: string | null) {
    const query = { ...options.route.query }
    if (field) query.groupBy = field
    else delete query.groupBy
    options.router.replace({ query })
  }

  function applySort(key: string) {
    options.sortOrder.value =
      options.sortKey.value === key && options.sortOrder.value === 'asc' ? 'desc' : 'asc'
    options.sortKey.value = key
    options.router.replace({ query: { ...options.route.query, sort: key, order: options.sortOrder.value } })
  }

  return {
    applyRouteState,
    setGroupByInRoute,
    applySort,
  }
}