import { useViewSetting } from '@/core/composables/useViewSetting'

/**
 * Per-user, per-doctype override of which fields show as quick filters - on the
 * server with the user's other list settings (useViewSetting), localStorage as
 * a cache. Never touches DocType metadata, so it never triggers a DocType save
 * (which would rewrite the doctype's JSON file and, in dev, restart the backend).
 *
 * null = no personal override, fall back to the doctype's admin-defined set
 * (fields flagged in_quick_filter).
 */
export function useQuickFilterPrefs(doctype: string) {
  const selectedFields = useViewSetting<string[]>(doctype, 'quick_filters', `grunt_quick_filters_v1_${doctype}`, {
    valid: (v): v is string[] => Array.isArray(v) && v.every((k) => typeof k === 'string'),
  })

  function setSelection(fields: string[]) {
    selectedFields.value = fields
  }

  function reset() {
    selectedFields.value = null
  }

  return { selectedFields, setSelection, reset }
}
