import type { ComputedRef, InjectionKey, Ref } from 'vue'

import type { ResolvedAction } from '@/core/actions'

/** A bulk dialog the standard list actions ask the selection bar to open. */
export type BulkRequest = 'edit' | 'delete' | 'fast-delete' | null

/**
 * Handed from the list page to the selection bar (BulkActionBar), which sits
 * a few components down: the `bulk` actions to render, and a request slot
 * `listview.bulk_edit()` / `bulk_delete()` / `fast_delete()` write to.
 */
export interface ListBulkUi {
  actions: ComputedRef<ResolvedAction[]>
  request: Ref<BulkRequest>
}

export const LIST_BULK_UI: InjectionKey<ListBulkUi> = Symbol('list-bulk-ui')
