import client from './client'
import { useAuthStore } from '@/stores/auth'
import type { ReportDetail, ReportResult, ReportSummary } from '@/types'

// Report is a regular registered DocType, so list/get/create/update/delete
// go through the generic `/api/v1/docs/Report` CRUD (see grunt/api/v1/docs/crud.py) —
// no bespoke REST route exists or is needed for those. Only `run` and
// `exportXlsxUrl` are real RPC-only behavior (arbitrary query/script
// execution, xlsx generation), dispatched via `/api/v1/method/...`
// (grunt/reports/doctypes/Report/report.py: run / export_xlsx).
//
// Identifier split: CRUD operations key off the doctype's internal `name`
// (the generic REST contract), while `run`/`exportXlsxUrl` key off the
// human `report_name` field — `ReportEngine.run` looks reports up by
// `report_name`, and every existing reference to a report elsewhere in the
// app (dashboard shortcuts, sidebar links, the `report_url()` scripting
// helper) already stores/uses `report_name`, not the internal id.

export const reportsApi = {
  list: (): Promise<ReportSummary[]> =>
    client.get('/api/v1/docs/Report', { params: { per_page: 1000 } }).then(r => r.data.data),

  /** Look up a report by its `report_name` (see module doc for why). */
  get: async (reportName: string): Promise<ReportDetail> => {
    const r = await client.get('/api/v1/docs/Report', {
      params: { 'filter[report_name__eq]': reportName, per_page: 1 },
    })
    const row = r.data.data?.[0]
    if (!row) throw new Error(`Звіт '${reportName}' не знайдено`)
    return row as ReportDetail
  },

  create: (payload: Partial<ReportDetail>): Promise<ReportDetail> =>
    client.post('/api/v1/docs/Report', payload).then(r => r.data.data),

  /** `name` is the doctype's internal id (from a prior list()/get() result). */
  update: (name: string, payload: Partial<ReportDetail>): Promise<ReportDetail> =>
    client.put(`/api/v1/docs/Report/${encodeURIComponent(name)}`, payload).then(r => r.data.data),

  /** `name` is the doctype's internal id (from a prior list()/get() result). */
  delete: (name: string): Promise<void> =>
    client.delete(`/api/v1/docs/Report/${encodeURIComponent(name)}`).then(() => undefined),

  run: (reportName: string, filters: Record<string, unknown> = {}): Promise<ReportResult> =>
    client
      .post('/api/v1/method/grunt.reports.doctypes.Report.report.run', { name: reportName, filters })
      .then(r => r.data.data),

  exportXlsxUrl: (reportName: string): string => {
    const auth = useAuthStore()
    return `/api/v1/method/grunt.reports.doctypes.Report.report.export_xlsx?name=${encodeURIComponent(reportName)}&token=${encodeURIComponent(auth.token ?? '')}`
  },
}
