import type { ComputedRef, InjectionKey } from 'vue'

/**
 * Handed from the list page to every list view's empty state: whether the
 * visible rows are narrowed by search / filters / quick filters, and how to
 * drop all of them - so "nothing found" can tell an empty DocType apart from
 * an over-filtered one and offer a one-click reset.
 */
export interface ListFilterReset {
  active: ComputedRef<boolean>
  clear: () => void
}

export const LIST_FILTER_RESET: InjectionKey<ListFilterReset> = Symbol('list-filter-reset')
