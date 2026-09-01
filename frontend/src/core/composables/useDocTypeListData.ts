import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import type { ComputedRef, Ref } from 'vue'
import type { ActiveFilter, DocType } from '@/types'
import type { ExportContext } from '@/core/io'
import type { ListColumn } from '@/core/composables/useListColumns'
import { docsApi } from '@/core/api/docs'
import { statusConfigOf } from '@/core/status'

interface UseDocTypeListDataOptions {
  doctype: string
  page: Ref<number>
  debouncedSearch: Ref<string>
  sortKey: Ref<string>
  sortOrder: Ref<'asc' | 'desc'>
  groupBy: Ref<string | null>
  activeFilters: Ref<ActiveFilter[]>
  /** Debounced raw fast filter map in backend format { 'field__op': 'value' } */
  debouncedQuickFilters?: ComputedRef<Record<string, string>> | Ref<Record<string, string>>
  visibleKeys: ComputedRef<string[]>
  visibleColumns: ComputedRef<ListColumn[]>
  dt: Ref<DocType | null>
}

export function useDocTypeListData(options: UseDocTypeListDataOptions) {
  const listFields = computed(() => {
    const fields = new Set([...options.visibleKeys.value, 'modified_at', 'docstatus'])
    if (options.groupBy.value) fields.add(options.groupBy.value)
    if (options.sortKey.value) fields.add(options.sortKey.value)
    if (options.dt.value?.status_field) fields.add(options.dt.value.status_field)
    if (options.dt.value?.image_field) fields.add(options.dt.value.image_field)
    return [...fields].join(',')
  })

  const { data, isLoading, isFetching } = useQuery({
    queryKey: computed(() => [
      'documents',
      options.doctype,
      options.page.value,
      options.debouncedSearch.value,
      options.sortKey.value,
      options.sortOrder.value,
      JSON.stringify(options.activeFilters.value),
      JSON.stringify(options.debouncedQuickFilters?.value ?? {}),
      options.groupBy.value,
      listFields.value,
    ]),
    queryFn: () => docsApi.list(options.doctype, {
      page: options.page.value,
      per_page: options.groupBy.value ? 100 : 20,
      search: options.debouncedSearch.value || undefined,
      sort: options.groupBy.value ?? options.sortKey.value ?? undefined,
      order: options.groupBy.value ? 'asc' : (options.sortKey.value ? options.sortOrder.value : undefined),
      filters: options.activeFilters.value,
      quickFilters: options.debouncedQuickFilters?.value,
      fields: listFields.value,
    }),
    refetchOnMount: 'always',
  })

  const meta = computed(() => data.value?.meta)
  const rows = computed(() => (data.value?.data ?? []) as Record<string, unknown>[])

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
    meta,
    rows,
    exportCtx,
  }
}
