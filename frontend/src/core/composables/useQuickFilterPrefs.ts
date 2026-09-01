import { ref } from 'vue'

/**
 * Per-user, per-doctype override of which fields show as quick filters.
 * Purely local (localStorage) — never touches DocType metadata, so it never
 * triggers a DocType save (which would rewrite the doctype's JSON file and,
 * in dev, restart the backend via --reload-include '*.json').
 *
 * null = no personal override, fall back to the doctype's admin-defined set
 * (explicit quick_filters + fields flagged in_quick_filter).
 */
export function useQuickFilterPrefs(doctype: string) {
  const storageKey = `grunt_quick_filters_v1_${doctype}`
  const saved = localStorage.getItem(storageKey)
  const selectedFields = ref<string[] | null>(saved ? (JSON.parse(saved) as string[]) : null)

  function setSelection(fields: string[]) {
    selectedFields.value = fields
    localStorage.setItem(storageKey, JSON.stringify(fields))
  }

  function reset() {
    selectedFields.value = null
    localStorage.removeItem(storageKey)
  }

  return { selectedFields, setSelection, reset }
}
