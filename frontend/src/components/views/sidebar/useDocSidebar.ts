/**
 * Data layer for the document detail sidebar.
 *
 * One bundle request (`docsApi.getSidebar`) replaces the previous
 * one-fetch-per-section waterfall. Mutations reuse the existing granular
 * endpoints and patch the local bundle optimistically.
 */
import { ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { docsApi, type SidebarBundle } from '@/core/api/docs'
import { authApi } from '@/core/api/auth-admin'
import type { Colleague } from '@/types'

const EMPTY: SidebarBundle = {
  assignees: [],
  shares: [],
  tags: [],
  bookmark: null,
  follow: null,
  people: {},
}

// Users are shared across all sidebar instances and rarely change within a session.
let usersCache: Colleague[] | null = null
// Tags already used on each DocType - suggestions for the tag picker.
const tagsCache = new Map<string, string[]>()

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
      /* silent - sidebar is non-critical */
    } finally {
      loading.value = false
    }
  }

  watch([dt, id], reload, { immediate: true })

  // Assignees
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

  // Shares
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

  // Tags
  async function addTag(tag: string): Promise<void> {
    const d = dt(); const i = id()
    const value = tag.trim()
    if (!d || !i || !value) return
    if (bundle.value.tags.some((t) => t.tag?.toLowerCase() === value.toLowerCase())) return
    const created = await docsApi.addTag(d, i, value)
    bundle.value.tags = [...bundle.value.tags, { name: String(created.name), tag: value }]
    const known = tagsCache.get(d)
    if (known && !known.includes(value)) known.push(value)
  }
  async function removeTag(name: string): Promise<void> {
    await docsApi.removeTag(name)
    bundle.value.tags = bundle.value.tags.filter((t) => t.name !== name)
  }
  async function knownTags(): Promise<string[]> {
    const d = dt()
    if (!d) return []
    if (!tagsCache.has(d)) {
      try {
        const res = await docsApi.list('DocTag', { fields: 'tag', rawFilters: { reference_doctype: d }, per_page: 500 })
        tagsCache.set(d, [...new Set(res.data.map((r) => String(r.tag ?? '')).filter(Boolean))].sort())
      } catch {
        return []
      }
    }
    return tagsCache.get(d)!
  }

  // Bookmark
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

  // Follow (notifications about changes / comments)
  async function toggleFollow(): Promise<void> {
    const d = dt(); const i = id()
    if (!d || !i) return
    if (bundle.value.follow) {
      await docsApi.delete('DocFollow', bundle.value.follow.name)
      bundle.value.follow = null
    } else {
      const row = await docsApi.create('DocFollow', { reference_doctype: d, reference_id: i })
      bundle.value.follow = { name: String(row.name) }
    }
  }

  // People display helpers
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

  // Reminders (personal "remind me")
  async function addReminder(remindAt: string, description = ''): Promise<void> {
    const d = dt()
    const i = id()
    if (!d || !i) return
    const row = await docsApi.addReminder(d, i, remindAt, description)
    const list = [...(bundle.value.reminders ?? []), {
      name: row.name, remind_at: row.remind_at, description: row.description ?? null,
    }]
    list.sort((a, b) => String(a.remind_at).localeCompare(String(b.remind_at)))
    bundle.value = { ...bundle.value, reminders: list }
  }

  async function removeReminder(name: string): Promise<void> {
    await docsApi.delete('Reminder', name)
    bundle.value = {
      ...bundle.value,
      reminders: (bundle.value.reminders ?? []).filter((r) => r.name !== name),
    }
  }

  // User search (assign / share pickers)
  async function searchUsers(query: string): Promise<Colleague[]> {
    if (!usersCache) {
      try {
        usersCache = await authApi.listColleagues()
      } catch {
        return []
      }
    }
    const q = query.trim().toLowerCase()
    if (!q) return usersCache
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
    knownTags,
    toggleBookmark,
    toggleFollow,
    addReminder,
    removeReminder,
    searchUsers,
    personName,
    personAvatar,
    personInitials,
  }
}

export type DocSidebarState = ReturnType<typeof useDocSidebar>
