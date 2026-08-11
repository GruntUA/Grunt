import type { VueQueryPluginOptions } from '@tanstack/vue-query'

export const vueQueryOptions: VueQueryPluginOptions = {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        retry: 2,
        retryDelay: 1_000,
      },
    },
  },
}
