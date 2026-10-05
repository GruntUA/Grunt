/**
 * Paginated, searchable, filterable file listing backed by vue-query's
 * `useInfiniteQuery`. Shared by the attachment picker's Library channel and the
 * desk File Manager page. Inputs may be plain values, refs, or getters.
 *
 * vue-query owns cancellation and caching: changing search / category / sort
 * swaps the query key, so a slow in-flight page for the previous key can no
 * longer land in the current result set.
 */
import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useInfiniteQuery } from '@tanstack/vue-query'
import { filesApi, type FileItem, type FileListParams, type FileSortField } from '@/core/api/files'

export type FileCategory = 'all' | 'image' | 'pdf' | 'document'

/** Server-side `filters` fragments per category - no client-side filtering. */
const CATEGORY_FILTERS: Record<Exclude<FileCategory, 'all'>, Partial<FileListParams>> = {
  image: { contentTypeLike: 'image/' },
  pdf: { contentTypes: ['application/pdf'] },
  document: {
    contentTypes: [
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-powerpoint',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      'text/plain',
      'text/csv',
      'application/rtf',
    ],
  },
}

export interface UseFileListOptions {
  search?: MaybeRefOrGetter<string>
  category?: MaybeRefOrGetter<FileCategory>
  /** Document a file may be attached to - used only when `scopedToDoc` is on. */
  attachedToDoctype?: MaybeRefOrGetter<string | undefined>
  attachedToId?: MaybeRefOrGetter<string | undefined>
  /** Restrict the list to files attached to the document above. */
  scopedToDoc?: MaybeRefOrGetter<boolean>
  orderBy?: MaybeRefOrGetter<FileSortField>
  order?: MaybeRefOrGetter<'asc' | 'desc'>
  pageSize?: number
  enabled?: MaybeRefOrGetter<boolean>
}

export function useFileList(opts: UseFileListOptions = {}) {
  const pageSize = opts.pageSize ?? 30

  const params = computed<FileListParams>(() => {
    const category = toValue(opts.category) ?? 'all'
    const categoryFilter = category === 'all' ? {} : CATEGORY_FILTERS[category]
    const scoped = toValue(opts.scopedToDoc) ?? false
    return {
      search: toValue(opts.search)?.trim() || '',
      orderBy: toValue(opts.orderBy) ?? 'created_at',
      order: toValue(opts.order) ?? 'desc',
      attachedToDoctype: scoped ? toValue(opts.attachedToDoctype) : undefined,
      attachedToId: scoped ? toValue(opts.attachedToId) : undefined,
      ...categoryFilter,
    }
  })

  const query = useInfiniteQuery({
    queryKey: computed(() => ['files', params.value] as const),
    queryFn: ({ pageParam }) =>
      filesApi.list({ ...params.value, page: pageParam as number, limit: pageSize }),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.items.length, 0)
      // Stop as soon as the server ran out of rows or we reached the (filtered)
      // total - never keep polling empty pages.
      if (lastPage.items.length === 0) return undefined
      return loaded < lastPage.total ? allPages.length + 1 : undefined
    },
    enabled: computed(() => toValue(opts.enabled) ?? true),
    refetchOnMount: 'always',
  })

  const items = computed<FileItem[]>(() =>
    (query.data.value?.pages ?? []).flatMap(p => p.items),
  )
  const total = computed(() => query.data.value?.pages?.[0]?.total ?? 0)

  return {
    items,
    total,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    isError: query.isError,
    error: query.error,
    hasNextPage: query.hasNextPage,
    fetchNextPage: query.fetchNextPage,
    refetch: query.refetch,
  }
}
