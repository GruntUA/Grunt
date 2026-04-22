import { watch, type Ref } from 'vue'

import type { QueryClient } from '@tanstack/vue-query'

interface UseFormDocWatcherParams {
  lastMessage: Ref<unknown>
  isDirty: Ref<boolean>
  doctype: string
  id: string | null
  queryClient: QueryClient
  toast: { info: (message: string) => void }
}

export function useFormDocWatcher(params: UseFormDocWatcherParams) {
  watch(params.lastMessage, (msg) => {
    if (!msg || typeof msg !== 'object') return

    const message = msg as Record<string, unknown>
    if (message.event !== 'doc_change' || params.isDirty.value) return

    const data = message.data as Record<string, unknown> | undefined
    if (data?.source !== 'import') {
      params.toast.info('Документ оновлено іншим користувачем')
    }

    params.queryClient.invalidateQueries({
      queryKey: ['document', params.doctype, params.id],
    })
  })
}
