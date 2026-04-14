import type { Exporter, ExportContext } from './registry'
import { useAuthStore } from '@/stores/auth'

export const excelExporter: Exporter = {
  id: 'excel',
  label: 'Завантажити Excel',
  icon: 'Sheet',
  export(ctx: ExportContext) {
    const auth = useAuthStore()
    const url = `/api/v1/docs/${ctx.doctypeName}/export/xlsx?token=${auth.token}`
    const a = document.createElement('a')
    a.href = url
    a.download = ''
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  },
}
