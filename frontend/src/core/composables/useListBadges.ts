import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { docsApi, type ListBadge } from '@/core/api/docs'

/**
 * Comment / like counters for the rows on screen - one request per list page.
 * `doctype` empty -> nothing is fetched (tables outside a DocType list).
 */
export function useListBadges(doctype: MaybeRefOrGetter<string | undefined>, ids: MaybeRefOrGetter<string[]>) {
  const queryClient = useQueryClient()
  const queryKey = computed(() => ['list-badges', toValue(doctype), toValue(ids).join('\u0000')])

  const { data } = useQuery({
    queryKey,
    queryFn: () => docsApi.getListBadges(toValue(doctype)!, toValue(ids)),
    enabled: computed(() => !!toValue(doctype) && toValue(ids).length > 0),
  })

  const badges = computed<Record<string, ListBadge>>(() => data.value ?? {})

  async function toggleLike(id: string) {
    const dt = toValue(doctype)
    if (!dt) return
    const key = queryKey.value
    const prev = queryClient.getQueryData<Record<string, ListBadge>>(key)
    const cur = prev?.[id] ?? { comments: 0, likes: 0, liked: false }
    const optimistic = { ...cur, liked: !cur.liked, likes: Math.max(0, cur.likes + (cur.liked ? -1 : 1)) }
    queryClient.setQueryData(key, { ...prev, [id]: optimistic })
    try {
      const res = await docsApi.toggleLike(dt, id)
      queryClient.setQueryData(key, (old: Record<string, ListBadge> | undefined) => ({
        ...old, [id]: { ...optimistic, ...res },
      }))
    } catch {
      // The client interceptor already toasts the error - just undo.
      queryClient.setQueryData(key, prev)
    }
  }

  return { badges, toggleLike }
}
