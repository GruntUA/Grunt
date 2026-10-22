import type { Exporter, ExportContext } from './registry'
import { filtersToRaw } from '@/core/api/docs'
import { N_ } from '@/plugins/i18n'
import { useAuthStore } from '@/stores/auth'

// Rendered on the server: grunt/io/exporters/html.py + templates/list_export.html.
export const htmlExporter: Exporter = {
  id: 'html',
  label: N_('Export HTML'),
  icon: 'FileCode',
  export(ctx: ExportContext) {
    const auth = useAuthStore()
    const params = new URLSearchParams({
      doctype: ctx.doctypeName,
      fmt: 'html',
      token: auth.token ?? '',
      fields: ctx.columns.map(c => c.key).join(','),
    })
    if (ctx.filters.length) {
      params.set('filters', JSON.stringify(filtersToRaw(ctx.filters)))
      params.set('filter_summary', ctx.filters
        .map(f => f.op.startsWith('is ') ? `${f.label} ${f.op}` : `${f.label} ${f.op} ${f.displayValue || f.value}`)
        .join(' · '))
    }
    if (ctx.search) params.set('search', ctx.search)
    if (ctx.groupBy) params.set('group_by', ctx.groupBy)
    else if (ctx.sortKey) {
      params.set('sort_by', ctx.sortKey)
      if (ctx.sortOrder) params.set('sort_order', ctx.sortOrder)
    }

    const a = document.createElement('a')
    a.href = `/api/v1/method/grunt.document.base.Document.export_file?${params}`
    a.download = ''
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  },
}
