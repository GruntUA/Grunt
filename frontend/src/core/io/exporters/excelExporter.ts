import { N_ } from '@/plugins/i18n'
import type { Exporter, ExportContext } from './registry'
import { useAuthStore } from '@/stores/auth'

export const excelExporter: Exporter = {
  id: 'excel',
  label: N_('Download Excel'),
  icon: 'Sheet',
  export(ctx: ExportContext) {
    const auth = useAuthStore()
    const url = `/api/v1/method/grunt.document.base.Document.export_file?doctype=${ctx.doctypeName}&token=${auth.token}`
    const a = document.createElement('a')
    a.href = url
    a.download = ''
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  },
}
