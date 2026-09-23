/**
 * Data layer for the document detail sidebar.
 *
 * One bundle request (`docsApi.getSidebar`) replaces the previous
 * one-fetch-per-section waterfall. Mutations reuse the existing granular
 * endpoints and patch the local bundle optimistically.
 */
import { ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { docsApi, type SidebarBundle } from '@/core/api/docs'
import { authAdminApi } from '@/core/api/auth-admin'
import type { UserPublic } from '@/types'

const EMPTY: SidebarBundle = {
  assignees: [],
  shares: [],
  tags: [],
  bookmark: null,
  people: {},
}

// Users are shared across all sidebar instances and rarely change within a session.
let usersCache: UserPublic[] | null = null

export function useDocSidebar(
  doctype: MaybeRefOrGetter<string | undefined>,
  docId: MaybeRefOrGetter<string | undefined>,
) {
  const bundle = ref<SidebarBundle>({ ...EMPTY })
  const loading = ref(false)
  const loaded = ref(false)

  const dt = () => toValue(doctype)
  const id = () => toValue(docId)

  async function reload(): Promise<void> {
    const d = dt()
    const i = id()
    if (!d || !i) {
      bundle.value = { ...EMPTY }
      loaded.value = false
      return
    }
    loading.value = true
    try {
      bundle.value = await docsApi.getSidebar(d, i)
      loaded.value = true
    } catch {
      /* silent — sidebar is non-critical */
    } finally {
      loading.value = false
    }
  }

  watch([dt, id], reload, { immediate: true })

  // ── Assignees ──────────────────────────────────────────────────────────────
  async function assign(user: string, description?: string): Promise<void> {
    const d = dt(); const i = id()
    if (!d || !i || !user.trim()) return
    await docsApi.assign(d, i, user.trim(), description)
    await reload()
  }
  async function unassign(name: string): Promise<void> {
    await docsApi.unassign(name)
    bundle.value.assignees = bundle.value.assignees.filter((a) => a.name !== name)
  }

  // ── Shares ─────────────────────────────────────────────────────────────────
  async function share(user: string, permission: 'Read' | 'Write'): Promise<void> {
    const d = dt(); const i = id()
    if (!d || !i || !user.trim()) return
    await docsApi.share(d, i, user.trim(), permission)
    await reload()
  }
  async function unshare(name: string): Promise<void> {
    await docsApi.unshare(name)
    bundle.value.shares = bundle.value.shares.filter((s) => s.name !== name)
  }

  // ── Tags ───────────────────────────────────────────────────────────────────
  async function addTag(tag: string): Promise<void> {
    const d = dt(); const i = id()
    const value = tag.trim()
    if (!d || !i || !value) return
    if (bundle.value.tags.some((t) => t.tag?.toLowerCase() === value.toLowerCase())) return
    const created = await docsApi.addTag(d, i, value)
    bundle.value.tags = [...bundle.value.tags, { name: String(created.name), tag: value }]
  }
  async function removeTag(name: string): Promise<void> {
    await docsApi.removeTag(name)
    bundle.value.tags = bundle.value.tags.filter((t) => t.name !== name)
  }

  // ── Bookmark ───────────────────────────────────────────────────────────────
  async function toggleBookmark(title: string): Promise<void> {
    const d = dt(); const i = id()
    if (!d || !i) return
    if (bundle.value.bookmark) {
      await docsApi.removeBookmark(d, i)
      bundle.value.bookmark = null
    } else {
      bundle.value.bookmark = await docsApi.addBookmark(d, i, title)
    }
  }

  // ── People display helpers ────────────────────────────────────────────────
  function personName(email?: string | null): string {
    if (!email) return '—'
    return bundle.value.people[email]?.name || email
  }
  function personAvatar(email?: string | null): string | null {
    if (!email) return null
    return bundle.value.people[email]?.avatar ?? null
  }
  function personInitials(email?: string | null): string {
    const n = personName(email)
    const parts = n.split(/[\s@.]+/).filter(Boolean)
    return (parts[0]?.[0] ?? '?').concat(parts[1]?.[0] ?? '').toUpperCase()
  }

  // ── User search (assign / share pickers) ───────────────────────────────────
  async function searchUsers(query: string): Promise<UserPublic[]> {
    if (!usersCache) {
      try {
        usersCache = await authAdminApi.listUsers()
      } catch {
        return []
      }
    }
    const q = query.trim().toLowerCase()
    if (!q) return []
    return usersCache.filter(
      (u) =>
        u.email.toLowerCase().includes(q) ||
        (u.full_name && u.full_name.toLowerCase().includes(q)),
    )
  }

  return {
    bundle,
    loading,
    loaded,
    reload,
    assign,
    unassign,
    share,
    unshare,
    addTag,
    removeTag,
    toggleBookmark,
    searchUsers,
    personName,
    personAvatar,
    personInitials,
  }
}
