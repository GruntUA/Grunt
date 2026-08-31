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
      },
    },
  },
}
