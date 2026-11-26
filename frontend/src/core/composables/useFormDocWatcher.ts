import { ref, type Ref } from 'vue'

import type { QueryClient } from '@tanstack/vue-query'
import i18n from '@/plugins/i18n'

const t = (key: string, params: Record<string, unknown> = {}): string => i18n.global.t(key, params)

interface UseFormDocWatcherParams {
  /** The document room's socket (`useWebSocket`). */
  onEvent: (event: string, handler: (data: unknown) => void) => unknown
  isDirty: Ref<boolean>
  doctype: string
  id: string | null
  queryClient: QueryClient
  toast: { info: (message: string) => void }
  /** The form's copy of the document - its `modified_at` tells an own save. */
  document: Ref<Record<string, unknown> | null | undefined>
  /** The signed-in user's email. */
  userEmail: () => string | null | undefined
}

/** Two timestamps of the same instant (`+00:00` vs `Z`, micro- vs milliseconds). */
function sameInstant(a: unknown, b: unknown): boolean {
  if (typeof a !== 'string' || typeof b !== 'string') return false
  const x = Date.parse(a)
  return !Number.isNaN(x) && x === Date.parse(b)
}

/**
 * Realtime events of the document's room (`grunt.activity.live`):
 *
 * - `doc_change` - the document was saved elsewhere: reload it, unless the
 *   form holds unsaved edits or already shows that very save (its own);
 * - `timeline_change` - a comment, file, letter or assignment changed.
 *
 * Both bump `timelineRefreshKey`, which the sidebar timeline watches.
 */
export function useFormDocWatcher(params: UseFormDocWatcherParams) {
  const timelineRefreshKey = ref(0)

  params.onEvent('doc_change', (raw) => {
    timelineRefreshKey.value++
    if (params.isDirty.value) return

    const data = (raw ?? {}) as Record<string, unknown>
    if (data.source === 'save' && sameInstant(data.modified_at, params.document.value?.modified_at)) return

    const byOther = data.source !== 'import' && (!data.modified_by || data.modified_by !== params.userEmail())
    if (byOther) {
      params.toast.info(t('The document was updated by another user'))
    }

    params.queryClient.invalidateQueries({
      queryKey: ['document', params.doctype, params.id],
    })
  })

  params.onEvent('timeline_change', () => {
    timelineRefreshKey.value++
  })

  return { timelineRefreshKey }
}
