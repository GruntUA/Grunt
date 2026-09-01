import { computed } from 'vue'
import { useInfiniteQuery } from '@tanstack/vue-query'
import type { ComputedRef, Ref } from 'vue'
import type { ActiveFilter, DocType } from '@/types'
import type { ExportContext } from '@/core/io'
import type { ListColumn } from '@/core/composables/useListColumns'
import { docsApi } from '@/core/api/docs'
import { statusConfigOf } from '@/core/status'

interface UseInfiniteDocTypeListDataOptions {
  doctype: string
  debouncedSearch: Ref<string>
  sortKey: Ref<string>
  sortOrder: Ref<'asc' | 'desc'>
  groupBy: Ref<string | null>
  activeFilters: Ref<ActiveFilter[]>
  debouncedFastFilters?: ComputedRef<Record<string, string>> | Ref<Record<string, string>>
  visibleKeys: ComputedRef<string[]>
  visibleColumns: ComputedRef<ListColumn[]>
  dt: Ref<DocType | null>
}

export function useInfiniteDocTypeListData(options: UseInfiniteDocTypeListDataOptions) {
  const listFields = computed(() => {
    const fields = new Set([...options.visibleKeys.value, 'modified_at', 'docstatus'])
    if (options.groupBy.value) fields.add(options.groupBy.value)
    if (options.sortKey.value) fields.add(options.sortKey.value)
    if (options.dt.value?.status_field) fields.add(options.dt.value.status_field)
    if (options.dt.value?.image_field) fields.add(options.dt.value.image_field)
    return [...fields].join(',')
  })

  const { data, isLoading, isFetching, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: computed(() => [
      'documents',
      options.doctype,
      options.debouncedSearch.value,
      options.sortKey.value,
      options.sortOrder.value,
      JSON.stringify(options.activeFilters.value),
      JSON.stringify(options.debouncedFastFilters?.value ?? {}),
      options.groupBy.value,
      listFields.value,
    ]),
    queryFn: ({ pageParam }) => docsApi.list(options.doctype, {
      page: pageParam as number,
      per_page: options.groupBy.value ? 100 : 20,
      search: options.debouncedSearch.value || undefined,
      sort: options.groupBy.value ?? options.sortKey.value ?? undefined,
      order: options.groupBy.value ? 'asc' : (options.sortKey.value ? options.sortOrder.value : undefined),
      filters: options.activeFilters.value,
      fastFilters: options.debouncedFastFilters?.value,
      fields: listFields.value,
    }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      const meta = lastPage?.meta
      if (!meta) return undefined
      return meta.page < meta.pages ? meta.page + 1 : undefined
    },
    refetchOnMount: 'always',
  })

  // meta from the first page carries the stable total count
  const meta = computed(() => data.value?.pages?.[0]?.meta)

  const rows = computed(() =>
    (data.value?.pages ?? []).flatMap(p => (p.data ?? []) as Record<string, unknown>[]),
  )

  const exportCtx = computed<ExportContext>(() => ({
    doctypeName: options.doctype,
    doctypeLabel: options.dt.value?.label ?? options.doctype,
    rows: rows.value,
    columns: options.visibleColumns.value,
    fields: options.dt.value?.fields ?? [],
    filters: options.activeFilters.value,
    statusConfig: statusConfigOf(options.dt.value),
    total: meta.value?.total ?? rows.value.length,
    groupBy: options.groupBy.value,
    getAll: async () => {
      const total = meta.value?.total ?? 0
      const result = await docsApi.list(options.doctype, {
        page: 1,
        per_page: Math.min(total, 10_000),
        search: options.debouncedSearch.value || undefined,
        sort: options.groupBy.value ?? options.sortKey.value ?? undefined,
        order: options.groupBy.value ? 'asc' : (options.sortKey.value ? options.sortOrder.value : undefined),
        filters: options.activeFilters.value,
        fields: listFields.value,
      })
      return result.data as Record<string, unknown>[]
    },
  }))

  return {
    data,
    isLoading,
    isFetching,
    isFetchingNextPage,
    fetchNextPage,
    hasNextPage,
    meta,
    rows,
    exportCtx,
  }
}
