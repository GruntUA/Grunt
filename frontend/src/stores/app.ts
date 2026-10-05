import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { workspaceApi } from '@/core/api/workspace'
import type { Workspace, WorkspaceLink } from '@/core/api/workspace'

export interface SidebarGroup {
  section: string
  items: WorkspaceLink[]
}

/** Skip a sidebar-count refetch if the last successful one for this workspace is younger than this. */
const COUNTS_TTL = 30_000
/** Don't paint a persisted count cache older than this - stale-by-days numbers are worse than none. */
const COUNTS_CACHE_MAX_AGE = 24 * 60 * 60 * 1000
const COUNTS_CACHE_KEY = 'grunt:sidebar-counts'

type CountsCache = Record<string, { data: Record<string, number>; ts: number }>

function readCountsCache(): CountsCache {
  try {
    return JSON.parse(localStorage.getItem(COUNTS_CACHE_KEY) || '{}') as CountsCache
  } catch {
    return {}
  }
}

function writeCountsCache(cache: CountsCache): void {
  try {
    localStorage.setItem(COUNTS_CACHE_KEY, JSON.stringify(cache))
  } catch {
    // private mode / quota exceeded - the in-memory copy still works this session
  }
}

function buildGroups(items: WorkspaceLink[]): SidebarGroup[] {
  const groups: SidebarGroup[] = []
  let current: SidebarGroup | null = null

  for (const item of items) {
    if (item.type === 'Divider') {
      groups.push({ section: '__divider__', items: [] })
      current = null
    } else {
      if (item.section && item.section !== (current ? current.section : '')) {
        current = { section: item.section, items: [] }
        groups.push(current)
      } else if (!current) {
        current = { section: '', items: [] }
        groups.push(current)
      }
      current.items.push(item)
    }
  }
  return groups
}

export const useAppStore = defineStore('app', () => {
  const workspaces = ref<Workspace[]>([])
  const active = ref<Workspace | null>(null)
  const counts = ref<Record<string, number>>({})
  const loading = ref(false)
  const _stale = ref(new Set<string>())
  /** workspace name -> timestamp of its last successful get_counts call */
  const _countsFetchedAt = ref<Record<string, number>>({})

  function markStale(name: string) {
    _stale.value.add(name)
  }

  async function loadAll() {
    loading.value = true
    try {
      workspaces.value = await workspaceApi.list()
    } finally {
      loading.value = false
    }
  }

  async function setActive(name: string, forceRefresh = false) {
    const isStale = _stale.value.delete(name)
    const cached = workspaces.value.find(w => w.name === name)
    if (cached && !forceRefresh && !isStale) {
      active.value = cached
    } else {
      try {
        const fresh = await workspaceApi.get(name)
        active.value = fresh
        // update cache
        const idx = workspaces.value.findIndex(w => w.name === name)
        if (idx !== -1) workspaces.value[idx] = fresh
      } catch {
        active.value = null
        return
      }
    }
    // Paint cached counts instantly, then refresh in the background so the
    // sidebar never flashes empty badges on a cold load / workspace switch.
    const cachedCounts = readCountsCache()[name]
    counts.value = cachedCounts && Date.now() - cachedCounts.ts < COUNTS_CACHE_MAX_AGE ? cachedCounts.data : {}
    await refreshCounts(forceRefresh)
  }

  async function refreshCounts(force = false) {
    if (!active.value) return
    const name = active.value.name
    if (!force && Date.now() - (_countsFetchedAt.value[name] ?? 0) < COUNTS_TTL) return
    try {
      const fresh = await workspaceApi.getCounts(name)
      counts.value = fresh
      _countsFetchedAt.value[name] = Date.now()
      const cache = readCountsCache()
      cache[name] = { data: fresh, ts: Date.now() }
      writeCountsCache(cache)
    } catch {
      // Keep whatever we already show (cached or previous) rather than blanking every badge.
    }
  }

  function clearActive() {
    active.value = null
    counts.value = {}
  }

  const groupedItems = computed<SidebarGroup[]>(() => {
    if (!active.value) return []
    const raw = active.value.items
    const items = (Array.isArray(raw) ? raw : []) as WorkspaceLink[]
    if (items.length === 0) return []
    const sorted = [...items].sort((a, b) => (a.sequence || 0) - (b.sequence || 0))
    return buildGroups(sorted)
  })

  return { workspaces, active, counts, loading, loadAll, setActive, refreshCounts, clearActive, groupedItems, markStale }
})
