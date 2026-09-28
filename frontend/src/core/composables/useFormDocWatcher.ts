import { watch, type Ref } from 'vue'

import type { QueryClient } from '@tanstack/vue-query'
import i18n from '@/plugins/i18n'

const t = (key: string): string => i18n.global.t(key)

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
      params.toast.info(t('The document was updated by another user'))
    }

    params.queryClient.invalidateQueries({
      queryKey: ['document', params.doctype, params.id],
    })
  })
}
