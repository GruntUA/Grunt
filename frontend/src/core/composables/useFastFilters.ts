import { computed, watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { FastFilter } from '@/types'

export interface UseFastFiltersReturn {
  /** Raw backend-format filter map { "field__op": "value" } */
  rawFastFilters: ComputedRef<Record<string, string>>
  /** Set one fast-filter value by its id */
  setFastFilterValue: (id: string, value: string) => void
  /** Replace all fast-filter values at once */
  setFastFilters: (values: Record<string, string>) => void
}

/**
 * Computes backend-format fast filters from metadata defs and a shared values ref.
 *
 * The caller owns `fastFilterValues` (e.g. from useListViewState) so state
 * persists independently of this composable.
 *
 * @param defs             Reactive list of FastFilter definitions
 * @param scope            'list' or 'tree' — only filters with matching enabled_in are active
 * @param fastFilterValues External ref containing { [filterId]: value }
 */
export function useFastFilters(
  defs: ComputedRef<FastFilter[]> | Ref<FastFilter[]>,
  scope: 'list' | 'tree',
  fastFilterValues: Ref<Record<string, string>>,
): UseFastFiltersReturn {
  // Apply default_values from defs when they change (e.g. on DocType load)
  watch(
    defs,
    (newDefs) => {
      for (const ff of newDefs) {
        if (!ff.enabled_in.includes(scope)) continue
        if (!(ff.id in fastFilterValues.value) && ff.default_value != null) {
          fastFilterValues.value = {
            ...fastFilterValues.value,
            [ff.id]: String(ff.default_value),
          }
        }
      }
    },
    { immediate: true },
  )

  const rawFastFilters = computed<Record<string, string>>(() => {
    const result: Record<string, string> = {}
    const knownIds = new Set(defs.value.map(ff => ff.id))

    for (const ff of defs.value) {
      if (!ff.enabled_in.includes(scope)) continue
      const val = fastFilterValues.value[ff.id]
      if (val !== undefined && val !== '' && val !== null) {
        result[`${ff.field}__${ff.operator}`] = val
      }
    }

    // Script escape hatch: allow raw backend filter keys (field__op) directly
    // in fastFilterValues, e.g. listview.set_fast_filter_value('valid_from__lte_or_null', '2026-04-01').
    for (const [key, val] of Object.entries(fastFilterValues.value)) {
      if (knownIds.has(key)) continue
      if (!key.includes('__')) continue
      if (val !== undefined && val !== '' && val !== null) {
        result[key] = val
      }
    }

    return result
  })

  function setFastFilterValue(id: string, value: string) {
    fastFilterValues.value = { ...fastFilterValues.value, [id]: value }
  }

  function setFastFilters(values: Record<string, string>) {
    fastFilterValues.value = { ...values }
  }

  return { rawFastFilters, setFastFilterValue, setFastFilters }
}
