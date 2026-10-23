import type { InjectionKey, Ref } from 'vue'

/** A bulk dialog the standard list actions ask BulkActionDialogs to open. */
export type BulkRequest = 'edit' | 'delete' | 'fast-delete' | null

/**
 * Handed from the list page to the bulk dialogs (BulkActionDialogs), which sit
 * a few components down: a request slot `listview.bulk_edit()` /
 * `bulk_delete()` / `fast_delete()` write to.
 */
export interface ListBulkUi {
  request: Ref<BulkRequest>
}

export const LIST_BULK_UI: InjectionKey<ListBulkUi> = Symbol('list-bulk-ui')
