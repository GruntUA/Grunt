import type { ComputedRef, InjectionKey } from 'vue'

/**
 * The document whose Table field holds the rows being edited - for row field
 * editors that need it (e.g. a permission rule's row condition lists the
 * fields of the DocType being edited).
 */
export const PARENT_DOC: InjectionKey<ComputedRef<Record<string, unknown> | undefined>> =
  Symbol('table-parent-doc')
