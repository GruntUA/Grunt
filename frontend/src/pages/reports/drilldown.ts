/**
 * Drill-down helpers for List reports: turn a summary row into list-view URL
 * filters (see ReportView.vue and grunt/reports/engine.py `meta.drilldown`).
 */

/** Report filter-key suffix → list-view URL operator (see useListRouteSync OP_MAP). */
/** Report filter-key suffix → list-view URL operator (see useListRouteSync OP_MAP). */
const URL_OP: Record<string, string> = {
    '': 'eq', eq: 'eq', ne: 'ne', like: 'ilike', ilike: 'ilike',
    gt: 'gt', lt: 'lt', gte: 'gte', lte: 'lte', child_of: 'child_of',
}

export function addUrlFilters(query: Record<string, string>, filters: Record<string, unknown>) {
    for (const [key, value] of Object.entries(filters)) {
        const [field, op = ''] = key.split('__')
        const urlOp = URL_OP[op]
        // The list URL can't express in / not in / is-set — such a condition
        // just doesn't narrow the drill-down list.
        if (!urlOp || Array.isArray(value) || typeof value === 'boolean') continue
        query[`filter[${field}__${urlOp}]`] = String(value)
    }
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
