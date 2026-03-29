import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { workspaceApi } from '@/core/api/workspace'
import type { Workspace, WorkspaceLink } from '@/core/api/workspace'

export interface SidebarGroup {
  section: string
  items: WorkspaceLink[]
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

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspaces = ref<Workspace[]>([])
  const active = ref<Workspace | null>(null)
  const counts = ref<Record<string, number>>({})
  const loading = ref(false)

  async function loadAll() {
    loading.value = true
    try {
      workspaces.value = await workspaceApi.list()
    } finally {
      loading.value = false
    }
  }

  async function setActive(name: string) {
    const cached = workspaces.value.find(w => w.name === name)
    if (cached) {
      active.value = cached
    } else {
      try {
        active.value = await workspaceApi.get(name)
      } catch {
        active.value = null
        return
      }
    }
    await refreshCounts()
  }

  async function refreshCounts() {
    if (!active.value) return
    try {
      counts.value = await workspaceApi.getCounts(active.value.name)
    } catch {
      counts.value = {}
    }
  }

  function clearActive() {
    active.value = null
    counts.value = {}
  }

  const groupedItems = computed<SidebarGroup[]>(() => {
    if (!active.value) return []
    const raw = active.value.items
    const items = (Array.isArray(raw) ? raw : []) as unknown as WorkspaceLink[]
    const sorted = items.slice().sort((a, b) => a.sequence - b.sequence)
    return buildGroups(sorted)
  })

  return { workspaces, active, counts, loading, loadAll, setActive, refreshCounts, clearActive, groupedItems }
})
