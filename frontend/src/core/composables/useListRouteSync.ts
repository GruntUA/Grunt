import { watch, nextTick } from 'vue'
import type { Ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import type { DocType } from '@/types'
import { OP_MAP, displayOp } from '@/core/api/docs'

interface UseListRouteSyncOptions {
  route: RouteLocationNormalizedLoaded
  router: Router
  viewMode: Ref<string>
  groupBy: Ref<string | null>
  sortKey: Ref<string>
  sortOrder: Ref<'asc' | 'desc'>
  activeFilters: Ref<any[]>
  quickFilterValues?: Ref<Record<string, string>>
  /** Search box text - set from `?q=` when a link is opened. */
  search?: Ref<string>
  /** Debounced copy of `search` - written to `?q=` so typing doesn't spam history replaces. */
  debouncedSearch?: Ref<string>
  validViews: readonly string[]
  getDefaultView: () => string
  dt: Ref<DocType | null>
}


export function useListRouteSync(options: UseListRouteSyncOptions) {
  // Prevents the route.query watcher from calling applyRouteState() when we
  // ourselves call router.replace (state->URL sync). Without this the loop is:
  // activeFilters changed -> router.replace -> route.query changed -> applyRouteState
  // -> activeFilters unchanged (same content) -> no further loop, but one extra call.
  let _syncingToUrl = false

  // Sync state -> URL
  watch([options.viewMode, options.activeFilters, options.quickFilterValues, options.debouncedSearch], () => {
    _syncingToUrl = true

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
    if (options.quickFilterValues) {
      Object.entries(options.quickFilterValues.value).forEach(([id, val]) => {
        if (val !== '' && val != null) query[`ff[${id}]`] = val
      })
    }

    // Search
    if (options.debouncedSearch) {
      const q = options.debouncedSearch.value.trim()
      if (q) query.q = q
      else delete query.q
    }

    options.router.replace({ query })
    // Clear the flag after Vue Router has updated route.query and watchers have fired
    nextTick(() => { _syncingToUrl = false })
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
        const op = displayOp(backendOp, String(value))

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
      // Only assign a new array when the filter content actually changed - avoids
      // triggering the state->URL sync watcher with an identical payload.
      const same =
        options.activeFilters.value.length === filters.length &&
        options.activeFilters.value.every((f, i) =>
          f.fieldname === filters[i].fieldname &&
          f.op === filters[i].op &&
          f.value === filters[i].value,
        )
      if (!same) {
        options.activeFilters.value = filters
      }
    }

    // Parse fast filter values from URL: ff[id]=value
    const ffValues: Record<string, string> = {}
    Object.entries(options.route.query).forEach(([key, value]) => {
      const match = key.match(/^ff\[(.+)\]$/)
      if (match && value) ffValues[match[1]] = String(value)
    })
    if (Object.keys(ffValues).length > 0 && options.quickFilterValues) {
      options.quickFilterValues.value = { ...options.quickFilterValues.value, ...ffValues }
    }

    // Search: q=text
    const urlSearch = options.route.query.q
    if (typeof urlSearch === 'string' && urlSearch && options.search && options.search.value.trim() !== urlSearch) {
      options.search.value = urlSearch
    }
  }

  // Apply URL -> state on mount (immediate) and whenever navigation changes the query
  // from outside this composable (e.g. router.push from a form's dashboard button).
  watch(
    () => options.route.query,
    () => {
      if (_syncingToUrl) return
      applyRouteState()
    },
    { deep: true, immediate: true },
  )

  function setGroupByInRoute(field: string | null) {
    const query = { ...options.route.query }
    if (field) query.groupBy = field
    else delete query.groupBy
    options.router.replace({ query })
  }

  function applySort(key: string) {
    if (!key) {
      // Reset sort
      options.sortKey.value = ''
      options.sortOrder.value = 'asc'
      const query = { ...options.route.query }
      delete query.sort
      delete query.order
      options.router.replace({ query })
      return
    }
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
