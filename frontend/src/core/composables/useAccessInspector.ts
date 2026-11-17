/**
 * The access inspector dialog - one per app (mounted in AppLayout), opened from
 * a form or list action: `grunt.check_access(doctype, name?)`.
 */
import { reactive } from 'vue'

const state = reactive({ open: false, doctype: '', name: null as string | null })

export function useAccessInspector() {
  function open(doctype: string, name?: string | null) {
    state.doctype = doctype
    state.name = name ?? null
    state.open = true
  }
  return { state, open }
}
