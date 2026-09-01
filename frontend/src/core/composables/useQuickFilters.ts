import { computed, watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { QuickFilter } from '@/types'

function currentLocalIsoDate(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function isTodayToken(value: string | null | undefined): boolean {
  if (value == null) return false
  const token = String(value).trim().toLowerCase()
  return token === 'today' || token === 'today()'
}

function resolveDefaultValue(ff: QuickFilter): string | null {
  if (ff.default_value == null) return null
  const raw = String(ff.default_value)
  if (ff.input_type === 'date') {
    const token = raw.trim().toLowerCase()
    if (token === 'today' || token === 'today()') {
      return currentLocalIsoDate()
    }
  }
  return raw
}

export interface UseQuickFiltersReturn {
  /** Raw backend-format filter map { "field__op": "value" } */
  rawQuickFilters: ComputedRef<Record<string, string>>
  /** Set one quick-filter value by its id */
  setQuickFilterValue: (id: string, value: string) => void
  /** Replace all quick-filter values at once */
  setQuickFilters: (values: Record<string, string>) => void
}

/**
 * Computes backend-format fast filters from metadata defs and a shared values ref.
 *
 * The caller owns `quickFilterValues` (e.g. from useListViewState) so state
 * persists independently of this composable.
 *
 * @param defs             Reactive list of QuickFilter definitions
 * @param scope            'list' or 'tree' — only filters with matching enabled_in are active
 * @param quickFilterValues External ref containing { [filterId]: value }
 */
export function useQuickFilters(
  defs: ComputedRef<QuickFilter[]> | Ref<QuickFilter[]>,
  scope: 'list' | 'tree',
  quickFilterValues: Ref<Record<string, string>>,
): UseQuickFiltersReturn {
  // Apply default_values from defs when they change (e.g. on DocType load)
  watch(
    defs,
    (newDefs) => {
      for (const ff of newDefs) {
        if (!ff.enabled_in.includes(scope)) continue
        const defaultValue = resolveDefaultValue(ff)
        const existing = quickFilterValues.value[ff.id]
        const hasKey = ff.id in quickFilterValues.value
        const shouldReapplyTodayDefault =
          hasKey && existing === '' && ff.input_type === 'date' && isTodayToken(ff.default_value)

        if ((!hasKey || shouldReapplyTodayDefault) && defaultValue != null) {
          quickFilterValues.value = {
            ...quickFilterValues.value,
            [ff.id]: defaultValue,
          }
        }
      }
    },
    { immediate: true },
  )

  const rawQuickFilters = computed<Record<string, string>>(() => {
    const result: Record<string, string> = {}
    const knownIds = new Set(defs.value.map(ff => ff.id))

    for (const ff of defs.value) {
      if (!ff.enabled_in.includes(scope)) continue
      const val = quickFilterValues.value[ff.id]
      if (val !== undefined && val !== '' && val !== null) {
        result[`${ff.field}__${ff.operator}`] = val
      }
    }

    // Script escape hatch: allow raw backend filter keys (field__op) directly
    // in quickFilterValues, e.g. listview.set_quick_filter_value('valid_from__lte_or_null', '2026-04-01').
    for (const [key, val] of Object.entries(quickFilterValues.value)) {
      if (knownIds.has(key)) continue
      if (!key.includes('__')) continue
      if (val !== undefined && val !== '' && val !== null) {
        result[key] = val
      }
    }

    return result
  })

  function setQuickFilterValue(id: string, value: string) {
    quickFilterValues.value = { ...quickFilterValues.value, [id]: value }
  }

  function setQuickFilters(values: Record<string, string>) {
    quickFilterValues.value = { ...values }
  }

  return { rawQuickFilters, setQuickFilterValue, setQuickFilters }
}
