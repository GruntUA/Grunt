import type { VueQueryPluginOptions } from '@tanstack/vue-query'
import axios from 'axios'

/** Retry transient failures only — a 4xx (auth, permission, not found, bad request)
 *  won't change on retry, so fail fast instead of hammering the endpoint. */
function retry(failureCount: number, error: unknown): boolean {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    if (status && status >= 400 && status < 500) return false
  }
  return failureCount < 2
}

export const vueQueryOptions: VueQueryPluginOptions = {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        retry,
        retryDelay: 1_000,
        // Offline, still run the request — the service worker answers from its
        // cache (public/sw.js); TanStack's default would just pause it.
        networkMode: 'offlineFirst',
      },
      mutations: {
        // Never hold a mutation back while offline and fire it blindly later:
        // let it fail now so the offline queue (useOfflineQueue) keeps it with
        // a conflict check.
        networkMode: 'always',
      },
    },
  },
}
