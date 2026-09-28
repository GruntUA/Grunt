import type { Exporter, ExportContext } from './registry'
import { formatDate, formatDateTime, formatFull } from '@/core/datetime'
import i18n from '@/plugins/i18n'

const t = (key: string): string => i18n.global.t(key)

// Maps indicator color names → inline CSS values (mirrors global Badge variant colors)
const STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  default: { bg: '#f9fafb', text: '#6b7280', border: '#d1d5db' },
  secondary: { bg: '#f9fafb', text: '#6b7280', border: '#d1d5db' },
  success: { bg: '#f0fdf4', text: '#15803d', border: '#86efac' },
  info: { bg: '#eff6ff', text: '#1d4ed8', border: '#93c5fd' },
  warn: { bg: '#fffbeb', text: '#a16207', border: '#fcd34d' },
  danger: { bg: '#fef2f2', text: '#b91c1c', border: '#fca5a5' },
  contrast: { bg: '#111827', text: '#f9fafb', border: '#374151' },
  // Legacy colors for backward compatibility.
  gray: { bg: '#f9fafb', text: '#6b7280', border: '#d1d5db' },
  blue: { bg: '#eff6ff', text: '#1d4ed8', border: '#93c5fd' },
  green: { bg: '#f0fdf4', text: '#15803d', border: '#86efac' },
  yellow: { bg: '#fffbeb', text: '#a16207', border: '#fcd34d' },
  orange: { bg: '#fffbeb', text: '#a16207', border: '#fcd34d' },
  red: { bg: '#fef2f2', text: '#b91c1c', border: '#fca5a5' },
  purple: { bg: '#f5f3ff', text: '#6d28d9', border: '#c4b5fd' },
  pink: { bg: '#fdf2f8', text: '#be185d', border: '#f9a8d4' },
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function buildBadge(label: string, colorName: string): string {
  const c = STATUS_COLORS[colorName] ?? STATUS_COLORS.secondary
  return `<span style="display:inline-block;padding:2px 10px;border-radius:9999px;font-size:11px;font-weight:500;border:1px solid ${c.border};background:${c.bg};color:${c.text}">${escapeHtml(label)}</span>`
}

function buildSelectChip(label: string): string {
  return `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;background:#f3f4f6;border:1px solid #e5e7eb;color:#374151">${escapeHtml(label)}</span>`
}

function formatCellHtml(
  value: unknown,
  fieldtype: string,
  fieldname: string,
  statusField: string | null,
  indicatorMap: Map<string, { color: string; label?: string | null }>,
): string {
  if (value === null || value === undefined || value === '') {
    return '<span style="color:#d1d5db">—</span>'
  }

  const str = String(value)

  // Status field with configured indicator
  if (statusField === fieldname) {
    const ind = indicatorMap.get(str)
    if (ind) return buildBadge(ind.label ?? str, ind.color)
  }

  if (fieldtype === 'Check') {
    return str === '1' || str === 'true'
      ? '<span style="color:#16a34a;font-size:14px">✓</span>'
      : '<span style="color:#d1d5db;font-size:14px">✗</span>'
  }

  if (fieldtype === 'Date') {
    return escapeHtml(formatDate(str))
  }

  if (fieldtype === 'Datetime') {
    return escapeHtml(formatDateTime(str))
  }

  if (fieldtype === 'Rating') {
    const n = Math.round(parseFloat(str))
    if (!isNaN(n)) {
      const filled = '★'.repeat(Math.max(0, Math.min(n, 5)))
      const empty = '☆'.repeat(Math.max(0, 5 - Math.min(n, 5)))
      return `<span style="color:#f59e0b">${filled}</span><span style="color:#d1d5db">${empty}</span>`
    }
    return escapeHtml(str)
  }

  if (fieldtype === 'Select') {
    return buildSelectChip(str)
  }

  if (fieldtype === 'Geolocation') {
    if (typeof value === 'object' && value !== null && 'lat' in value && 'lng' in value) {
      const geo = value as { lat: number; lng: number }
      const lat = Number(geo.lat).toFixed(5)
      const lng = Number(geo.lng).toFixed(5)
      const mapsUrl = `https://www.google.com/maps?q=${lat},${lng}`
      return `<a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;gap:4px;font-family:monospace;font-size:11px;color:#1d4ed8;text-decoration:none" title="${escapeHtml(t('Open in Google Maps'))}"><svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>${lat}, ${lng}</a>`
    }
    return escapeHtml(str)
  }

  if (fieldtype === 'Color') {
    return `<span style="display:inline-flex;align-items:center;gap:6px"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${escapeHtml(str)};border:1px solid rgba(0,0,0,.15)"></span>${escapeHtml(str)}</span>`
  }

  return escapeHtml(str)
}

function renderRows(
  rows: Record<string, unknown>[],
  columns: ExportContext['columns'],
  fieldMap: Map<string, { fieldtype: string }>,
  statusField: string | null,
  indicatorMap: Map<string, { color: string; label?: string | null }>,
): string {
  return rows.map((row, ri) => {
    const cells = columns.map((col, ci) => {
      const ft = fieldMap.get(col.key)?.fieldtype ?? 'Text'
      const html = formatCellHtml(row[col.key], ft, col.key, statusField, indicatorMap)
      const firstCol = ci === 0 ? ' style="font-weight:600;color:#111827"' : ''
      return `<td${firstCol}>${html}</td>`
    }).join('')
    const bg = ri % 2 === 1 ? ' class="alt"' : ''
    return `<tr${bg}>${cells}</tr>`
  }).join('\n        ')
}

function groupRows(rows: Record<string, unknown>[], field: string): { key: string; items: Record<string, unknown>[] }[] {
  const map = new Map<string, Record<string, unknown>[]>()
  for (const row of rows) {
    const key = row[field] != null && row[field] !== '' ? String(row[field]) : ''
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(row)
  }
  return [...map.entries()].map(([key, items]) => ({ key, items }))
}

export function generateHtml(ctx: ExportContext): string {
  const { doctypeLabel, doctypeName, rows, columns, fields, filters, statusConfig, total, groupBy } = ctx

  const fieldMap = new Map(fields.map(f => [f.fieldname, f]))
  const statusField = statusConfig?.field ?? null
  const indicatorMap = new Map<string, { color: string; label?: string | null }>()
  for (const ind of statusConfig?.indicators ?? []) indicatorMap.set(ind.value, ind)

  const dateStr = formatFull(new Date())
  const isPartial = rows.length < total && total > 10_000

  const filterSummary = filters.length
    ? filters.map(f => f.op.startsWith('is ') ? `${f.label} ${f.op}` : `${f.label} ${f.op} ${f.displayValue || f.value}`).join(' · ')
    : null

  const headerCells = columns.map(c => `<th>${escapeHtml(c.label)}</th>`).join('')

  // ── Body: grouped or flat ──────────────────────────────────────────────────
  let bodyContent: string

  if (groupBy) {
    const groups = groupRows(rows, groupBy)
    bodyContent = groups.map(({ key, items }) => {
      const groupLabel = key || t('(no value)')
      let groupHeaderHtml: string
      if (statusField === groupBy) {
        const ind = indicatorMap.get(key)
        groupHeaderHtml = ind
          ? buildBadge((ind.label ?? key) || t('(no value)'), ind.color)
          : `<strong>${escapeHtml(groupLabel)}</strong>`
      } else {
        groupHeaderHtml = `<strong>${escapeHtml(groupLabel)}</strong>`
      }

      return `
      <tr class="group-header">
        <td colspan="${columns.length}" style="background:#f3f4f6;border-top:2px solid #e5e7eb;padding:8px 16px">
          <div style="display:flex;align-items:center;gap:8px">
            ${groupHeaderHtml}
            <span class="group-count">${items.length}</span>
          </div>
        </td>
      </tr>
      ${renderRows(items, columns, fieldMap, statusField, indicatorMap)}`
    }).join('\n')
  } else {
    bodyContent = renderRows(rows, columns, fieldMap, statusField, indicatorMap)
  }

  return `<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(doctypeLabel)} — ${escapeHtml(dateStr)}</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #374151;
      background: #f9fafb;
      padding: 32px 40px;
    }

    header { margin-bottom: 28px; }

    h1 {
      font-size: 26px;
      font-weight: 800;
      color: #111827;
      letter-spacing: -0.025em;
      margin-bottom: 8px;
    }

    .meta {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      font-size: 12px;
      color: #6b7280;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      padding: 2px 10px;
      background: #e5e7eb;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 600;
      color: #374151;
    }

    .chip.warning { background: #fef9c3; color: #854d0e; }

    .sep { color: #d1d5db; }

    .meta strong { color: #6b7280; font-weight: 600; }

    .table-wrap {
      background: #ffffff;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
      border: 1px solid #e5e7eb;
    }

    table { width: 100%; border-collapse: collapse; }

    thead {
      background: #f3f4f6;
      border-bottom: 2px solid #e5e7eb;
    }

    th {
      padding: 10px 16px;
      text-align: left;
      font-size: 10.5px;
      font-weight: 700;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      white-space: nowrap;
    }

    td {
      padding: 9px 16px;
      color: #374151;
      border-top: 1px solid #f3f4f6;
      vertical-align: top;
      max-width: 320px;
      word-break: break-word;
    }

    tr:first-child td { border-top: none; }
    tr.alt td { background: #fafafa; }
    tr:hover td { background: #f0f9ff !important; }

    tr.group-header td {
      font-size: 12px;
      font-weight: 700;
      color: #374151;
    }

    .group-count {
      display: inline-flex;
      align-items: center;
      padding: 1px 8px;
      background: #e5e7eb;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 600;
      color: #6b7280;
      margin-left: 6px;
    }

    footer {
      margin-top: 16px;
      font-size: 11px;
      color: #9ca3af;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    @media print {
      body { background: white; padding: 16px; font-size: 11px; }
      .table-wrap { box-shadow: none; }
      tr.alt td { background: #fafafa !important; }
      tr:hover td { background: inherit !important; }
    }
  </style>
</head>
<body>
  <header>
    <h1>${escapeHtml(doctypeLabel)}</h1>
    <div class="meta">
      <span class="chip">${escapeHtml(t('{n} records').replace('{n}', `${rows.length}${isPartial ? ` / ${total}` : ''}`))}</span>
      ${isPartial ? `<span class="chip warning">⚠ ${escapeHtml(t('Showing the first 10,000 records'))}</span>` : ''}
      <span class="sep">·</span>
      <span>${escapeHtml(dateStr)}</span>
      ${filterSummary ? `<span class="sep">·</span><span><strong>${escapeHtml(t('Filters'))}:</strong> ${escapeHtml(filterSummary)}</span>` : ''}
      ${groupBy ? `<span class="sep">·</span><span><strong>${escapeHtml(t('Grouping'))}:</strong> ${escapeHtml(fields.find(f => f.fieldname === groupBy)?.label ?? groupBy)}</span>` : ''}
    </div>
  </header>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>${headerCells}</tr>
      </thead>
      <tbody>
        ${bodyContent}
      </tbody>
    </table>
  </div>

  <footer>
    <span>${escapeHtml(doctypeName)}</span>
    <span>Grunt · ${escapeHtml(dateStr)}</span>
  </footer>
</body>
</html>`
}

function triggerDownload(html: string, filename: string) {
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const htmlExporter: Exporter = {
  id: 'html',
  label: 'Export HTML',
  icon: 'FileCode',
  async export(ctx: ExportContext) {
    const allRows = await ctx.getAll()
    const html = generateHtml({ ...ctx, rows: allRows })
    triggerDownload(html, `${ctx.doctypeName}_${new Date().toISOString().slice(0, 10)}.html`)
  },
}
