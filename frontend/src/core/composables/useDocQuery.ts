/**
 * Centralized TanStack Query hooks for Grunt documents.
 *
 * Provides reactive, cached data fetching with standardized query keys.
 * All components should prefer these hooks over raw docsApi calls.
 *
 * @example
 * // Single document
 * const { data: user, isPending } = useDoc<UserDoc>('User', userId)
 *
 * // List with reactive filters
 * const params = computed(() => ({ page: 1, search: q.value }))
 * const { data } = useDocList('Customer', params)
 *
 * // Mutation
 * const { mutate: save, isPending: isSaving } = useDocSave('Customer')
 * save({ id, ...fields })
 */

import { computed, toValue } from 'vue'
import type { MaybeRefOrGetter } from 'vue'
import {
    useQuery,
    useMutation,
    useQueryClient,
    type UseQueryOptions,
} from '@tanstack/vue-query'
import { docsApi, type ListParams } from '@/core/api'
import type { GruntDocument } from '@/types'

// ── Query key factory ────────────────────────────────────────────────────────

export const docKeys = {
    /** All queries for a doctype: ['docs', 'Customer'] */
    all: (doctype: string) => ['docs', doctype] as const,
    /** All list queries for a doctype */
    lists: (doctype: string) => ['docs', doctype, 'list'] as const,
    /** Specific list with params */
    list: (doctype: string, params: object) =>
        ['docs', doctype, 'list', params] as const,
    /** Single document detail */
    detail: (doctype: string, id: string) =>
        ['docs', doctype, id] as const,
}

// ── Single document ──────────────────────────────────────────────────────────

/**
 * Fetch a single document by id. Result is cached and deduplicated.
 */
export function useDoc<T extends GruntDocument = GruntDocument>(
    doctype: string,
    id: MaybeRefOrGetter<string | null | undefined>,
    options?: Partial<UseQueryOptions<T>>,
) {
    return useQuery<T>({
        queryKey: computed(() => docKeys.detail(doctype, toValue(id) ?? '')),
        queryFn: () => docsApi.get<T>(doctype, toValue(id)!),
        enabled: computed(() => !!toValue(id)),
        staleTime: 30_000,
        ...options,
    })
}

// ── Document list ────────────────────────────────────────────────────────────

/**
 * Fetch a paginated/filtered list of documents.
 * `params` can be a reactive ref — query re-runs automatically on change.
 */
export function useDocList(
    doctype: string,
    params: MaybeRefOrGetter<ListParams> = {},
) {
    return useQuery({
        queryKey: computed(() => docKeys.list(doctype, toValue(params))),
        queryFn: () => docsApi.list(doctype, toValue(params)),
        staleTime: 30_000,
        placeholderData: (prev) => prev,  // keep old data visible while refetching
    })
}

// ── Mutations with cache invalidation ────────────────────────────────────────

/**
 * Create a new document. Invalidates the list cache on success.
 */
export function useDocCreate<T extends GruntDocument = GruntDocument>(
    doctype: string,
) {
    const qc = useQueryClient()
    return useMutation({
        mutationFn: (data: Record<string, unknown>) =>
            docsApi.create<T>(doctype, data),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: docKeys.lists(doctype) })
        },
    })
}

/**
 * Update an existing document. Optimistically updates the cache.
 */
export function useDocUpdate<T extends GruntDocument = GruntDocument>(
    doctype: string,
) {
    const qc = useQueryClient()
    return useMutation({
        mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
            docsApi.update<T>(doctype, id, data),
        onSuccess: (updated) => {
            // Update detail cache immediately
            qc.setQueryData(docKeys.detail(doctype, updated.name), updated)
            // Invalidate lists so counts/order stay fresh
            qc.invalidateQueries({ queryKey: docKeys.lists(doctype) })
        },
    })
}

/**
 * Delete a document. Removes it from cache and invalidates lists.
 */
export function useDocDelete(doctype: string) {
    const qc = useQueryClient()
    return useMutation({
        mutationFn: (id: string) => docsApi.delete(doctype, id),
        onSuccess: (_data, id) => {
            qc.removeQueries({ queryKey: docKeys.detail(doctype, id) })
            qc.invalidateQueries({ queryKey: docKeys.lists(doctype) })
        },
    })
}

/**
 * Convenience: save = create if no id, update if id present.
 */
export function useDocSave<T extends GruntDocument = GruntDocument>(
    doctype: string,
) {
    const qc = useQueryClient()
    return useMutation({
        mutationFn: ({ id, ...data }: { id?: string } & Record<string, unknown>) =>
            id
                ? docsApi.update<T>(doctype, id, data)
                : docsApi.create<T>(doctype, data),
        onSuccess: (saved) => {
            qc.setQueryData(docKeys.detail(doctype, saved.name), saved)
            qc.invalidateQueries({ queryKey: docKeys.lists(doctype) })
        },
    })
}

// ── Link search ──────────────────────────────────────────────────────────────

/**
 * Reactive link field search with debounce-friendly query key.
 */
export function useLinkSearch(
    doctype: MaybeRefOrGetter<string>,
    query: MaybeRefOrGetter<string>,
    filters: MaybeRefOrGetter<Record<string, string | string[]>> = {},
    pageLength = 10,
) {
    return useQuery({
        queryKey: computed(() => [
            'link-search',
            toValue(doctype),
            toValue(query),
            toValue(filters),
        ]),
        queryFn: () =>
            docsApi.linkSearch(toValue(doctype), toValue(query), toValue(filters), pageLength),
        enabled: computed(() => toValue(query).length >= 0),
        staleTime: 10_000,
    })
}
