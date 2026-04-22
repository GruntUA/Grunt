import { watch } from 'vue'
import type { Ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'

interface UseListRouteSyncOptions {
  route: RouteLocationNormalizedLoaded
  router: Router
  viewMode: Ref<string>
  groupBy: Ref<string | null>
  sortKey: Ref<string>
  sortOrder: Ref<'asc' | 'desc'>
  validViews: readonly string[]
  getDefaultView: () => string
}

export function useListRouteSync(options: UseListRouteSyncOptions) {
  watch(options.viewMode, (v) => {
    const query = { ...options.route.query }
    if (v === options.getDefaultView()) delete query.view
    else query.view = v
    options.router.replace({ query })
  })

  function applyRouteState() {
    const urlView = options.route.query.view as string | undefined

    if (urlView && options.validViews.includes(urlView)) {
      options.viewMode.value = urlView
    } else if (!options.validViews.includes(options.viewMode.value)) {
      options.viewMode.value = options.getDefaultView()
    }

    if (options.route.query.groupBy) options.groupBy.value = options.route.query.groupBy as string
    if (options.route.query.sort) options.sortKey.value = options.route.query.sort as string
    if (['asc', 'desc'].includes(options.route.query.order as string)) {
      options.sortOrder.value = options.route.query.order as 'asc' | 'desc'
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