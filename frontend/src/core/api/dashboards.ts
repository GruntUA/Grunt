import type { Dashboard, DashboardSummary, DashboardWidget } from '@/types'
import client from './client'

export const dashboardApi = {
  list: async (workspace?: string): Promise<DashboardSummary[]> => {
    const r = await client.get('/api/v1/dashboards/', { params: workspace ? { workspace } : {} })
    return r.data.data
  },

  get: async (name: string): Promise<Dashboard> => {
    const r = await client.get(`/api/v1/dashboards/${name}`)
    return r.data.data
  },

  create: async (payload: Partial<Dashboard>): Promise<Dashboard> => {
    const r = await client.post('/api/v1/dashboards/', payload)
    return r.data.data
  },

  update: async (name: string, payload: Partial<Dashboard>): Promise<Dashboard> => {
    const r = await client.put(`/api/v1/dashboards/${name}`, payload)
    return r.data.data
  },

  delete: async (name: string): Promise<void> => {
    await client.delete(`/api/v1/dashboards/${name}`)
  },

  getData: async (name: string): Promise<Record<string, unknown>> => {
    const r = await client.get(`/api/v1/dashboards/${name}/data`)
    return r.data.data
  },
}
