import client from './client'
import type { ReportDetail, ReportResult, ReportSummary } from '@/types'

export const reportsApi = {
  list: (): Promise<{ success: boolean; data: ReportSummary[] }> =>
    client.get('/api/v1/reports/').then(r => r.data),

  get: (name: string): Promise<{ success: boolean; data: ReportDetail }> =>
    client.get(`/api/v1/reports/${encodeURIComponent(name)}`).then(r => r.data),

  create: (payload: Partial<ReportDetail>): Promise<{ success: boolean; data: { id: string; report_name: string } }> =>
    client.post('/api/v1/reports/', payload).then(r => r.data),

  update: (name: string, payload: Partial<ReportDetail>): Promise<{ success: boolean }> =>
    client.put(`/api/v1/reports/${encodeURIComponent(name)}`, payload).then(r => r.data),

  delete: (name: string): Promise<{ success: boolean }> =>
    client.delete(`/api/v1/reports/${encodeURIComponent(name)}`).then(r => r.data),

  run: (name: string, filters: Record<string, unknown> = {}): Promise<{ success: boolean } & ReportResult> =>
    client.post(`/api/v1/reports/${encodeURIComponent(name)}/run`, { filters }).then(r => r.data),

  exportXlsxUrl: (name: string): string =>
    `/api/v1/reports/${encodeURIComponent(name)}/export/xlsx`,
}
