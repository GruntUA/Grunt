import { computed, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { DocField, DocType } from '@/types'
import { getFieldDef } from '@/core/fieldRegistry'

interface UseGroupingParams {
  dt: Ref<DocType | null>
  rows: ComputedRef<Record<string, unknown>[]>
  groupBy: Ref<string | null>
  page: Ref<number>
}

export function useGrouping({ dt, rows, groupBy, page }: UseGroupingParams) {
  const collapsedGroups = ref<Set<string>>(new Set())

  const groupableFields = computed(() => {
    if (!dt.value) return []
    return dt.value.fields.filter((f: DocField) => {
      if (f.hidden) return false
      const def = getFieldDef(f.fieldtype)
      if (!def) return false
      if (def.is_layout || def.non_groupable) return false
      return f.in_list_view || f.in_filter
    })
  })

  const groupedRows = computed(() => {
    if (!groupBy.value) return null
    const field = groupBy.value
    const groups = new Map<string, Record<string, unknown>[]>()
    for (const row of rows.value) {
      const key = String(row[field] ?? '')
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(row)
    }
    return [...groups.entries()].map(([key, items]) => ({ key, items }))
  })

  const groupByField = computed(
    () => groupableFields.value.find((f) => f.fieldname === groupBy.value) ?? null,
  )

  function setGroupBy(field: string | null) {
    groupBy.value = field
    collapsedGroups.value = new Set()
    page.value = 1
  }

  return {
    collapsedGroups,
    groupableFields,
    groupedRows,
    groupByField,
    setGroupBy,
  }
}
