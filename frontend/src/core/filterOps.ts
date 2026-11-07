/**
 * Filter operators - the one frontend vocabulary.
 *
 * A *display* operator (`'='`, `'like'`, `'is set'`) is what the filter bar,
 * report conditions and saved filters store; the backend gets it as a
 * filter-key suffix: `{ "amount__gte": 5 }` (see grunt/query/parse.py).
 *
 * Backend mirror of this table: `DISPLAY_OPS` in grunt/query/parse.py
 * (tests/unit/test_filter_ops_sync.py keeps the two in step).
 *
 * Which operators a field type offers is decided in core/filterRegistry.ts.
 */
import { N_ } from '@/plugins/i18n'
import type { ActiveFilter } from '@/types'

interface OpDef {
  /** Backend suffix: `field__<backend>`. */
  backend: string
  /** i18n key of the full label ("Greater than"). */
  label: string
  /** Short form for compact UIs ("≥"); defaults to the label. */
  short?: string
  /** Fixed value sent instead of a user-entered one (`field__is=set`). */
  fixedValue?: string
  /** The value is a comma-separated list (`field__in=a,b`). */
  multi?: boolean
}

export const FILTER_OPS = {
  '=': { backend: 'eq', label: N_('Equals'), short: '=' },
  '!=': { backend: 'ne', label: N_('Not equals'), short: '≠' },
  '>': { backend: 'gt', label: N_('Greater than'), short: '>' },
  '<': { backend: 'lt', label: N_('Less than'), short: '<' },
  '>=': { backend: 'gte', label: N_('Greater than or equal'), short: '≥' },
  '<=': { backend: 'lte', label: N_('Less than or equal'), short: '≤' },
  'like': { backend: 'ilike', label: N_('Contains') },
  'not like': { backend: 'nlike', label: N_('Does not contain') },
  'in': { backend: 'in', label: N_('Is one of'), multi: true },
  'not in': { backend: 'nin', label: N_('Is none of'), multi: true },
  'is set': { backend: 'is', label: N_('Is set'), fixedValue: 'set' },
  'is not set': { backend: 'is', label: N_('Is empty'), fixedValue: 'not set' },
  // Expanded to the subtree (`field__in=…`) by list queries and reports, not by grunt.db.
  'child_of': { backend: 'child_of', label: N_('Descendant of') },
} as const satisfies Record<string, OpDef>

export type FilterOp = keyof typeof FILTER_OPS

const DEFS = FILTER_OPS as Record<string, OpDef>
const ENTRIES = Object.entries(DEFS)

/** Display operator -> backend suffix. */
export const OP_MAP: Record<string, string> = Object.fromEntries(ENTRIES.map(([op, d]) => [op, d.backend]))

/** Operators whose value is a comma-separated list (`field__in=a,b`). */
export const MULTI_VALUE_OPS: string[] = ENTRIES.filter(([, d]) => d.multi).map(([op]) => op)

/** Operators without a user-entered value - the value is fixed and sent as `field__is=<value>`. */
export const NO_VALUE_OPS: Record<string, string> = Object.fromEntries(
  ENTRIES.filter(([, d]) => d.fixedValue).map(([op, d]) => [op, d.fixedValue!]),
)

/**
 * Every suffix the backend understands (grunt/query/parse.py FILTER_OPS plus
 * `child_of`), longest first so `__lte_or_null` wins over `__lte`.
 */
const BACKEND_SUFFIXES = [
  'lte_or_null', 'child_of', 'isnull', 'nlike', 'like', 'ilike', 'gte', 'lte', 'nin',
  'neq', 'year', 'gt', 'lt', 'eq', 'in', 'ne', 'is',
]

/** Backend aliases that mean the same as a display operator's suffix. */
const BACKEND_ALIASES: Record<string, string> = { like: 'ilike', neq: 'ne' }

/**
 * `"amount__gte"` -> `["amount", "gte"]`; no known suffix -> `[key, "eq"]`.
 * Same rule as `split_key` in grunt/query/parse.py: a field named `foo__bar` stays whole.
 */
export function splitFilterKey(key: string): [string, string] {
  for (const op of BACKEND_SUFFIXES) {
    if (key.endsWith(`__${op}`)) return [key.slice(0, -op.length - 2), op]
  }
  return [key, 'eq']
}

/**
 * Backend suffix -> the display operator for it, or `null` when the filter bar
 * can't show it (`isnull`, `year`, …). `is` splits by value.
 */
export function displayOpOrNull(backendOp: string, value?: string): string | null {
  const op = BACKEND_ALIASES[backendOp] ?? backendOp
  if (op === 'is') return value === 'set' ? 'is set' : 'is not set'
  return ENTRIES.find(([, d]) => d.backend === op)?.[0] ?? null
}

/** Backend `field__op` + value -> display operator (unknown -> `'='`). */
export function displayOp(backendOp: string, value: string): string {
  return displayOpOrNull(backendOp, value) ?? '='
}

/** `field` + display operator -> backend filter key (`amount__gte`). */
export function filterKey(fieldname: string, op: string): string {
  return `${fieldname}__${OP_MAP[op] ?? 'eq'}`
}

/** An operator's label; `short` gives the symbol (`≥`) where there is one. */
export function opLabel(op: string, t: (key: string) => string, short = false): string {
  const d = DEFS[op]
  if (!d) return op
  return short && d.short ? d.short : t(d.label)
}

/** Convert ActiveFilter[] to raw backend filter object: { "fieldname__op": "value" } */
export function filtersToRaw(filters: ActiveFilter[]): Record<string, string> {
  const raw: Record<string, string> = {}
  for (const f of filters) raw[filterKey(f.fieldname, f.op)] = f.value
  return raw
}
