import { ref, computed, watch } from 'vue'
import type { DocType, DocField } from '@/types'
import type { ListColumn } from '@/core/composables/useListColumns'
import { getNonPhysicalTypeSet } from '@/core/fieldRegistry'

/**
 * One entry of a `Report` (type=List) `columns` JSON — the same shape the
 * backend report engine consumes (grunt/reports/engine.py `_run_list_report`).
 * A column with no `aggregation` becomes a GROUP BY when any sibling has one.
 */
export interface ReportListColumn {
  fieldname: string
  label: string
  fieldtype?: string
  aggregation?: Exclude<AggFn, 'none'>
}

/**
 * Report view model — a "Report" grid over the list query.
 *
 * Pure logic only: which columns are shown, an optional single-level group-by,
 * a per-column aggregate function, and the derived grouped rows + subtotal /
 * grand-total lines. Rendering lives in ReportGridView.vue.
 *
 * State (columns / group / aggregates) is persisted per DocType in localStorage
 * under its own key, independent of the list view's column preferences.
 */

export type AggFn = 'none' | 'sum' | 'avg' | 'min' | 'max' | 'count'

/** Field types whose values can be summed / averaged. */
const NUMERIC = new Set(['Int', 'Float', 'Percent', 'Duration', 'Rating'])
const STRUCTURAL = getNonPhysicalTypeSet()

export function isNumericField(f: DocField | undefined): boolean {
  return !!f && NUMERIC.has(f.fieldtype)
}

/** Default aggregate for a freshly shown numeric column. */
function defaultAgg(f: DocField): AggFn {
  return f.fieldtype === 'Percent' || f.fieldtype === 'Rating' ? 'avg' : 'sum'
}

interface PersistShape {
  cols?: string[]
  group?: string | null
  aggs?: Record<string, AggFn>
}

export interface ReportGroup {
  key: string
  rows: Record<string, unknown>[]
  /** fieldname -> aggregated numeric value */
  aggregates: Record<string, number>
}

export interface ReportModelOptions {
  doctype: () => string
  dt: () => DocType | null
  listColumns: () => ListColumn[]
  rows: () => Record<string, unknown>[]
}

export function useReportModel(opts: ReportModelOptions) {
  const storageKey = computed(() => `grunt_report_v1_${opts.doctype()}`)

  const _persisted = ref<PersistShape>(readPersisted(storageKey.value))
  watch(storageKey, (k) => { _persisted.value = readPersisted(k) })

  function readPersisted(key: string): PersistShape {
    try {
      const raw = localStorage.getItem(key)
      return raw ? (JSON.parse(raw) as PersistShape) : {}
    } catch {
      return {}
    }
  }

  function persist() {
    try {
      localStorage.setItem(storageKey.value, JSON.stringify(_persisted.value))
    } catch { /* quota / private mode — non-fatal */ }
  }

  // ── Field lookup ───────────────────────────────────────────────────────────

  const fieldMap = computed<Record<string, DocField>>(() => {
    const m: Record<string, DocField> = {}
    for (const f of opts.dt()?.fields ?? []) m[f.fieldname] = f
    return m
  })

  /** Every field that may be shown as a report column. */
  const availableColumns = computed<ListColumn[]>(() =>
    (opts.dt()?.fields ?? [])
      .filter((f) => !STRUCTURAL.has(f.fieldtype) && !f.hidden)
      .map((f) => ({ key: f.fieldname, label: f.label, sortable: true })),
  )

  const defaultKeys = computed<string[]>(() => {
    const cols = opts.listColumns().map((c) => c.key)
    return cols.length ? cols : ['name']
  })

  const visibleKeys = computed<string[]>(() => {
    const saved = _persisted.value.cols
    const valid = new Set(availableColumns.value.map((c) => c.key))
    const keys = (saved ?? defaultKeys.value).filter((k) => valid.has(k))
    return keys.length ? keys : defaultKeys.value
  })

  const visibleColumns = computed<ListColumn[]>(() =>
    visibleKeys.value
      .map((k) => availableColumns.value.find((c) => c.key === k))
      .filter((c): c is ListColumn => c !== undefined),
  )

  function isVisible(key: string): boolean {
    return visibleKeys.value.includes(key)
  }

  function toggleColumn(key: string) {
    const cur = visibleKeys.value
    _persisted.value.cols = cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]
    persist()
  }

  function reorderColumns(oldIndex: number, newIndex: number) {
    const next = [...visibleKeys.value]
    const [moved] = next.splice(oldIndex, 1)
    next.splice(newIndex, 0, moved)
    _persisted.value.cols = next
    persist()
  }

  // ── Group by ──────────────────────────────────────────────────────────────

  const groupableFields = computed<DocField[]>(() =>
    (opts.dt()?.fields ?? []).filter(
      (f) => !STRUCTURAL.has(f.fieldtype) && !f.hidden && !NUMERIC.has(f.fieldtype),
    ),
  )

  const groupKey = computed<string | null>(() => _persisted.value.group ?? null)
  const groupField = computed<DocField | null>(() =>
    groupKey.value ? (fieldMap.value[groupKey.value] ?? null) : null,
  )

  function setGroupBy(key: string | null) {
    _persisted.value.group = key
    persist()
  }

  // ── Aggregates ────────────────────────────────────────────────────────────

  function aggFor(key: string): AggFn {
    const f = fieldMap.value[key]
    if (!isNumericField(f)) return 'none'
    return _persisted.value.aggs?.[key] ?? defaultAgg(f)
  }

  function setAgg(key: string, fn: AggFn) {
    const aggs = { ..._persisted.value.aggs }
    if (fn === defaultAgg(fieldMap.value[key] ?? ({} as DocField))) delete aggs[key]
    else aggs[key] = fn
    _persisted.value.aggs = aggs
    persist()
  }

  function reduce(rows: Record<string, unknown>[], key: string, fn: AggFn): number {
    const nums = rows
      .map((r) => Number(r[key]))
      .filter((n) => Number.isFinite(n))
    if (!nums.length) return 0
    switch (fn) {
      case 'avg': return nums.reduce((a, b) => a + b, 0) / nums.length
      case 'min': return Math.min(...nums)
      case 'max': return Math.max(...nums)
      case 'count': return nums.length
      case 'sum':
      default: return nums.reduce((a, b) => a + b, 0)
    }
  }

  function aggregatesOf(rows: Record<string, unknown>[]): Record<string, number> {
    const out: Record<string, number> = {}
    for (const col of visibleColumns.value) {
      const fn = aggFor(col.key)
      if (fn !== 'none') out[col.key] = reduce(rows, col.key, fn)
    }
    return out
  }

  // ── Derived model ─────────────────────────────────────────────────────────

  const groups = computed<ReportGroup[] | null>(() => {
    if (!groupKey.value) return null
    const gk = groupKey.value
    const buckets = new Map<string, Record<string, unknown>[]>()
    for (const row of opts.rows()) {
      const k = String(row[gk] ?? '')
      if (!buckets.has(k)) buckets.set(k, [])
      buckets.get(k)!.push(row)
    }
    return [...buckets.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([key, rows]) => ({ key, rows, aggregates: aggregatesOf(rows) }))
  })

  const grandTotals = computed<Record<string, number>>(() => aggregatesOf(opts.rows()))

  const hasAnyAggregate = computed(() =>
    visibleColumns.value.some((c) => aggFor(c.key) !== 'none'),
  )

  const isCustomized = computed(
    () => _persisted.value.cols !== undefined
      || !!_persisted.value.group
      || Object.keys(_persisted.value.aggs ?? {}).length > 0,
  )

  // ── Bridge: <-> saved `Report` (type=List) `columns` JSON ──────────────────

  /**
   * Serialize the current shape into a `Report` `List` `columns` array.
   *
   * With aggregates present the result is a *pivot*: the group field (if set)
   * plus every aggregated column — plain detail columns are dropped, because
   * the backend engine turns every non-aggregated column into a GROUP BY.
   * Without aggregates it is a plain detail listing of all visible columns.
   *
   * `droppedColumns` names the visible columns left out, for a UI hint.
   */
  function toReportColumns(): { columns: ReportListColumn[]; droppedColumns: string[] } {
    const cols = visibleColumns.value
    if (!hasAnyAggregate.value) {
      return {
        columns: cols.map((c) => ({
          fieldname: c.key,
          label: c.label,
          fieldtype: fieldMap.value[c.key]?.fieldtype ?? 'Text',
        })),
        droppedColumns: [],
      }
    }
    const gk = groupKey.value
    const out: ReportListColumn[] = []
    const dropped: string[] = []
    const gf = gk ? fieldMap.value[gk] : undefined
    if (gf) out.push({ fieldname: gf.fieldname, label: gf.label, fieldtype: gf.fieldtype })
    for (const c of cols) {
      if (c.key === gk) continue
      const fn = aggFor(c.key)
      if (fn !== 'none') {
        out.push({
          fieldname: c.key,
          label: c.label,
          aggregation: fn,
          fieldtype: fieldMap.value[c.key]?.fieldtype ?? 'Float',
        })
      } else {
        dropped.push(c.label)
      }
    }
    return { columns: out, droppedColumns: dropped }
  }

  /** Load a saved `Report` `List` `columns` array back into the model. */
  function applyReportColumns(cols: ReportListColumn[]) {
    const valid = new Set(availableColumns.value.map((c) => c.key))
    const keys = cols.map((c) => c.fieldname).filter((k) => valid.has(k))
    _persisted.value.cols = keys.length ? keys : undefined

    const aggregated = cols.filter((c) => c.aggregation)
    if (aggregated.length) {
      const g = cols.find((c) => !c.aggregation)
      _persisted.value.group = g && valid.has(g.fieldname) ? g.fieldname : null
      const aggs: Record<string, AggFn> = {}
      for (const c of aggregated) {
        if (valid.has(c.fieldname)) aggs[c.fieldname] = c.aggregation as AggFn
      }
      _persisted.value.aggs = aggs
    } else {
      _persisted.value.group = null
      _persisted.value.aggs = {}
    }
    persist()
  }

  return {
    toReportColumns,
    applyReportColumns,
    availableColumns,
    visibleColumns,
    visibleKeys,
    isVisible,
    toggleColumn,
    reorderColumns,
    groupableFields,
    groupKey,
    groupField,
    setGroupBy,
    aggFor,
    setAgg,
    groups,
    grandTotals,
    hasAnyAggregate,
    isCustomized,
    fieldMap,
  }
}
