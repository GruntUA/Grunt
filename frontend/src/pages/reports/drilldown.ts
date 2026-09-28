/**
 * Drill-down helpers for List reports: turn a summary row into list-view URL
 * filters (see ReportView.vue and grunt/reports/engine.py `meta.drilldown`).
 */
import type { RouteLocationRaw } from 'vue-router'
import { docUrl } from '@/core/workspaceUrl'

/** Report filter-key suffix → list-view URL operator (see OP_MAP in core/api/docs.ts). */
const URL_OP: Record<string, string> = {
    '': 'eq', eq: 'eq', ne: 'ne', like: 'ilike', ilike: 'ilike', nlike: 'nlike',
    gt: 'gt', lt: 'lt', gte: 'gte', lte: 'lte', child_of: 'child_of', is: 'is',
    in: 'in', nin: 'nin',
}

export function addUrlFilters(query: Record<string, string>, filters: Record<string, unknown>) {
    for (const [key, value] of Object.entries(filters)) {
        const [field, op = ''] = key.split('__')
        const urlOp = URL_OP[op]
        // The list URL can't express isnull / booleans — such a condition just
        // doesn't narrow the drill-down list. in / nin lists travel as CSV.
        if (!urlOp || typeof value === 'boolean') continue
        if (Array.isArray(value) && urlOp !== 'in' && urlOp !== 'nin') continue
        query[`filter[${field}__${urlOp}]`] = Array.isArray(value) ? value.join(',') : String(value)
    }
}

/** The doctype list narrowed by `filters` (grunt.db filter keys) — dashboard widget drill-down. */
export function filteredListUrl(
    doctype: string, filters: Record<string, unknown>, workspace?: string | null,
): RouteLocationRaw {
    const query: Record<string, string> = {}
    addUrlFilters(query, filters)
    return { path: docUrl(doctype, null, workspace), query }
}

/** Filter for one group of a group-by widget; the NULL group means "field is empty". */
export function groupFilter(field: string, key: unknown): Record<string, unknown> {
    return key === null || key === undefined ? { [`${field}__is`]: 'not set' } : { [field]: key }
}

/** `[from, to)` ISO dates of a date-group label: 2026-09-23 / 2026-09 / 2026-Q3 / 2026. */
export function periodRange(bucket: string, label: string): [string, string] | null {
    const iso = (d: Date) => d.toISOString().slice(0, 10)
    const utc = (y: number, m: number, d = 1) => new Date(Date.UTC(y, m, d))
    let m: RegExpMatchArray | null
    if (bucket === 'day' && (m = label.match(/^(\d{4})-(\d{2})-(\d{2})$/))) {
        const start = utc(+m[1], +m[2] - 1, +m[3])
        return [iso(start), iso(utc(+m[1], +m[2] - 1, +m[3] + 1))]
    }
    if (bucket === 'month' && (m = label.match(/^(\d{4})-(\d{2})$/))) {
        return [iso(utc(+m[1], +m[2] - 1)), iso(utc(+m[1], +m[2]))]
    }
    if (bucket === 'quarter' && (m = label.match(/^(\d{4})-Q([1-4])$/))) {
        const first = (+m[2] - 1) * 3
        return [iso(utc(+m[1], first)), iso(utc(+m[1], first + 3))]
    }
    if (bucket === 'year' && (m = label.match(/^(\d{4})$/))) {
        return [iso(utc(+m[1], 0)), iso(utc(+m[1] + 1, 0))]
    }
    return null
}
